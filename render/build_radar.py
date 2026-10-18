"""
Blender 5.x script: build the SENTINEL-UHF radar site and render it.

  blender -b -P build_radar.py -- [night|aerial] [samples]

Geometry follows the system design: two array faces 120 deg apart, each a
22 m active aperture tilted back 20 deg, carrying 2,587 crossed dipoles on a
0.41 m equilateral lattice (the same lattice as radar_sizing.py / the EM model).
"""
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SHOT = ARGS[0] if ARGS else "night"
SAMPLES = int(ARGS[1]) if len(ARGS) > 1 else 96
OUT = Path(__file__).parent

H_BLD, W_FACE, TILT = 32.0, 34.0, math.radians(20)
D_AP, LATTICE, STANDOFF = 22.0, 0.41, 0.18


# ------------------------------------------------------------------ helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, color, rough=0.6, metal=0.0, emission=None, strength=0.0, bump=None, noise_mix=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
        bsdf.inputs["Emission Strength"].default_value = strength
    if noise_mix or bump:
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = (noise_mix or {}).get("scale", 40.0)
        tex.inputs["Detail"].default_value = 8
    if noise_mix:
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*noise_mix["a"], 1)
        ramp.color_ramp.elements[1].color = (*noise_mix["b"], 1)
        nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if bump:
        bn = nt.nodes.new("ShaderNodeBump")
        bn.inputs["Strength"].default_value = bump
        nt.links.new(tex.outputs["Fac"], bn.inputs["Height"])
        nt.links.new(bn.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def mesh_obj(name, verts, faces, material=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    if material:
        ob.data.materials.append(material)
    return ob


def box_mesh(cx, cy, cz, sx, sy, sz, material, name="box", rot_z=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz), rotation=(0, 0, rot_z))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (sx, sy, sz)
    ob.data.materials.append(material)
    return ob


def cyl(p0, p1, r, material, name="cyl", verts=12):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d.length, location=(p0 + p1) / 2)
    ob = bpy.context.active_object
    ob.name = name
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = d.to_track_quat("Z", "Y")
    ob.data.materials.append(material)
    return ob


def sphere(p, r, material, name="sph"):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=p, segments=16, ring_count=8)
    ob = bpy.context.active_object
    ob.name = name
    ob.data.materials.append(material)
    return ob


def intersect(p1, d1, p2, d2):
    """2-D line intersection."""
    den = d1[0] * d2[1] - d1[1] * d2[0]
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])


# ------------------------------------------------------------------ scene
def build():
    M = {
        "concrete": mat("Concrete", (0.80, 0.81, 0.82), 0.7, bump=0.05,
                        noise_mix={"a": (0.74, 0.75, 0.77), "b": (0.84, 0.85, 0.86), "scale": 4}),
        "panel": mat("ArrayGround", (0.42, 0.42, 0.43), 0.6, 0.5),
        "dipole": mat("Dipole", (0.78, 0.78, 0.80), 0.35, 1.0),
        "gravel": mat("Gravel", (0.45, 0.4, 0.32), 0.95, bump=0.6,
                      noise_mix={"a": (0.3, 0.26, 0.2), "b": (0.6, 0.53, 0.42), "scale": 160}),
        "red": mat("Obstruction", (0.5, 0, 0), 0.4, emission=(1, 0.05, 0.02), strength=60),
        "lamp": mat("Lamp", (1, 1, 1), 0.3, emission=(1.0, 0.88, 0.72), strength=80),
        "steel": mat("Steel", (0.45, 0.46, 0.48), 0.45, 0.9),
        "clad": mat("Cladding", (0.32, 0.4, 0.5), 0.5, 0.4, bump=0.3, noise_mix={"a": (0.5, 0.6, 0.72), "b": (0.6, 0.7, 0.82), "scale": 3}),
        "window": mat("Window", (0.1, 0.2, 0.3), 0.2, emission=(0.45, 0.75, 1.0), strength=6),
        "tree": mat("Tree", (0.03, 0.06, 0.035), 0.9),
        "rope": mat("Rope", (0.85, 0.85, 0.85), 0.6),
    }

    # building plan: equilateral triangle (side S) with the front corner between the two
    # faces truncated by CF. Faces tilt back by TILT; back wall and truncation are vertical.
    # S = 48, CF = 15 gives a 33 m face whose top edge is 64 % of its base and which holds a
    # 28 m octagon (22 m active circle + terminated dummy elements) - the PAVE PAWS proportions.
    S, CF = 48.0, 15.0          # triangle side, front truncation between the faces
    n1 = (-math.sin(math.radians(60)), math.cos(math.radians(60)))
    n2 = (math.sin(math.radians(60)), math.cos(math.radians(60)))
    apex = (0.0, 0.0)
    BL = (apex[0] - S * 0.5, apex[1] - S * 0.866)
    BR = (apex[0] + S * 0.5, apex[1] - S * 0.866)
    t1 = ((BL[0] - apex[0]) / S, (BL[1] - apex[1]) / S)
    t2 = ((BR[0] - apex[0]) / S, (BR[1] - apex[1]) / S)
    F1a = (apex[0] + t1[0] * CF, apex[1] + t1[1] * CF)
    F2a = (apex[0] + t2[0] * CF, apex[1] + t2[1] * CF)
    base = [F1a, BL, BR, F2a]          # CCW; edges: face 1, back wall, face 2, front truncation
    tilted = {0: n1, 2: n2}
    import itertools
    planes = [(Vector((0, 0, -1)), 0.0), (Vector((0, 0, 1)), H_BLD)]   # (outward normal, c): n.X <= c
    for i in range(4):
        p, q = base[i], base[(i + 1) % 4]
        d = Vector((q[0] - p[0], q[1] - p[1], 0)).normalized()
        nrm = Vector((d.y, -d.x, 0))
        if i in tilted:
            nn = tilted[i]
            nrm = Vector((nn[0] * math.cos(TILT), nn[1] * math.cos(TILT), math.sin(TILT)))
        planes.append((nrm, nrm.dot(Vector((p[0], p[1], 0)))))
    pts = []
    for (a1, c1), (a2, c2), (a3, c3) in itertools.combinations(planes, 3):
        det = a1.dot(a2.cross(a3))
        if abs(det) < 1e-9:
            continue
        X = (a2.cross(a3) * c1 + a3.cross(a1) * c2 + a1.cross(a2) * c3) / det
        if all(nv.dot(X) <= cv + 1e-3 for nv, cv in planes):       # mathutils is float32
            if all((X - Q).length > 1e-3 for Q in pts):
                pts.append(X)
    top = [(P.x, P.y) for P in pts if abs(P.z - H_BLD) < 1e-3]
    me = bpy.data.meshes.new("Building")
    bm = bmesh.new()
    for P in pts:
        bm.verts.new(P)
    bmesh.ops.convex_hull(bm, input=bm.verts[:])
    bmesh.ops.dissolve_limit(bm, angle_limit=0.01, verts=bm.verts[:], edges=bm.edges[:])
    bm.to_mesh(me)
    bm.free()
    bld = bpy.data.objects.new("Building", me)
    bpy.context.collection.objects.link(bld)
    bld.data.materials.append(M["concrete"])
    bev = bld.modifiers.new("bevel", "BEVEL")
    bev.width = 0.15
    bev.segments = 2
    At, Lt, Rt = top[0], top[len(top) // 3], top[2 * len(top) // 3]
    face_defs = []
    for nn, a0, a1 in ((n1, F1a, BL), (n2, F2a, BR)):
        L = math.dist(a0, a1)
        face_defs.append((nn, ((a1[0] - a0[0]) / L, (a1[1] - a0[1]) / L), a0, L))
    global SITE
    SITE = {"apex": apex, "BL": BL, "BR": BR, "S": S}

    # array faces
    for k, (n, t, base0, wface) in enumerate(face_defs):
        n3 = Vector((n[0] * math.cos(TILT), n[1] * math.cos(TILT), math.sin(TILT)))
        u = Vector((t[0], t[1], 0)).normalized()
        vv = n3.cross(u).normalized()
        if vv.z < 0:
            vv = -vv
        centre = Vector((*base0, 0)) + u * 13.4 + vv * 16.0 + n3 * 0.02
        # octagonal array face, 28 m flat to flat: 22 m active circle + dummy elements
        R = 14.0
        oct_v = [centre + (u * math.cos(math.radians(22.5 + 45 * i)) + vv * math.sin(math.radians(22.5 + 45 * i))) * R / math.cos(math.radians(22.5)) for i in range(8)]
        oct_v = [p + n3 * 0.06 for p in oct_v]
        mesh_obj(f"Panel{k}", oct_v + [centre + n3 * 0.06], [tuple(range(8))], M["panel"])
        # crossed dipoles on the triangular lattice
        verts, quads = [], []
        rows = int(2 * R / (LATTICE * math.sqrt(3) / 2)) + 4
        cols = int(2 * R / LATTICE) + 4
        hw, arm = 0.012, 0.14
        count = 0
        for r in range(-rows // 2, rows // 2 + 1):
            for q in range(-cols // 2, cols // 2 + 1):
                x = q * LATTICE + (LATTICE / 2 if r % 2 else 0.0)
                y = r * LATTICE * math.sqrt(3) / 2
                # fill the octagon: active elements inside the 22 m circle, terminated
                # dummy elements in the corners (edge treatment, as on real arrays)
                ax, ay = abs(x), abs(y)
                if max(ax, ay, (ax + ay) / math.sqrt(2)) > R - 0.25:
                    continue
                count += 1
                p = centre + u * x + vv * y + n3 * STANDOFF
                for a_dir, b_dir, off in ((u, vv, 0.0), (vv, u, -0.02)):
                    c = p + n3 * off
                    i0 = len(verts)
                    for sa in (-arm, arm):
                        for sb in (-hw, hw):
                            for sc in (-hw, hw):
                                verts.append(c + a_dir * sa + b_dir * sb + n3 * sc)
                    quads += [(i0, i0 + 1, i0 + 3, i0 + 2), (i0 + 4, i0 + 6, i0 + 7, i0 + 5),
                              (i0, i0 + 4, i0 + 5, i0 + 1), (i0 + 2, i0 + 3, i0 + 7, i0 + 6),
                              (i0, i0 + 2, i0 + 6, i0 + 4), (i0 + 1, i0 + 5, i0 + 7, i0 + 3)]
                # feed post to ground plane
                c = p
                i0 = len(verts)
                for sb in (-0.015, 0.015):
                    for sc in (-0.015, 0.015):
                        verts.append(c + u * sb + vv * sc)
                        verts.append(c - n3 * (STANDOFF - 0.06) + u * sb + vv * sc)
                quads += [(i0, i0 + 1, i0 + 3, i0 + 2), (i0 + 4, i0 + 5, i0 + 7, i0 + 6),
                          (i0, i0 + 4, i0 + 5, i0 + 1), (i0 + 2, i0 + 3, i0 + 7, i0 + 6)]
        mesh_obj(f"Elements{k}", verts, quads, M["dipole"])
        print(f"face {k}: {count} elements")

    # obstruction lights and masts
    for p in top:
        sphere((p[0], p[1], H_BLD + 0.4), 0.35, M["red"], "RedLight")
    mast = Vector((sum(p[0] for p in top) / len(top), sum(p[1] for p in top) / len(top), H_BLD))
    cyl(mast, mast + Vector((0, 0, 6)), 0.08, M["steel"], "Mast")
    sphere(mast + Vector((0, 0, 6.2)), 0.3, M["red"], "RedLight")
    cyl(mast + Vector((3, 1, 0)), mast + Vector((3, 1, 3.5)), 0.05, M["steel"], "Mast2")

    # ground, fence, lamps, equipment building, tree line
    bpy.ops.mesh.primitive_plane_add(size=900, location=(0, 0, 0))
    g = bpy.context.active_object
    g.data.materials.append(M["gravel"])
    for k, (n, t, base0, wface) in enumerate(face_defs):
        base = Vector((base0[0] + t[0] * wface / 2, base0[1] + t[1] * wface / 2, 0)) - Vector((n[0], n[1], 0)) * 5
        along = Vector((t[0], t[1], 0))
        for i in range(-9, 10):
            p = base + along * (i * 3.2) + Vector((n[0], n[1], 0)) * 9
            cyl(p, p + Vector((0, 0, 1.15)), 0.04, M["rope"], "Post")
        a = base + along * (-9 * 3.2) + Vector((n[0], n[1], 0)) * 9 + Vector((0, 0, 1.05))
        b = base + along * (9 * 3.2) + Vector((n[0], n[1], 0)) * 9 + Vector((0, 0, 1.05))
        cyl(a, b, 0.012, M["rope"], "Rope", verts=6)
    # camera-relative placement (matches the reference photo: face 1 seen from front-left,
    # back wall grazing on the right, equipment buildings beyond it, light poles to the left)
    view_c = Vector((-0.993, -0.120, 0))              # from face 1 towards the camera
    right = Vector((0.120, -0.993, 0))                # screen right as seen from the camera
    fm = Vector((-15.75, -27.28, 0))                  # foot of face 1 centre
    for c_d, l_o in ((30, 22), (24, 36), (48, 44)):
        q = fm + view_c * c_d - right * l_o
        cyl((q.x, q.y, 0), (q.x, q.y, 10), 0.12, M["steel"], "Pole")
        sphere((q.x, q.y, 10.2), 0.35, M["lamp"], "LampHead")
        bpy.ops.object.light_add(type="POINT", location=(q.x, q.y, 9.7))
        L = bpy.context.active_object
        L.data.energy = 12000
        L.data.color = (0.92, 0.88, 1.0)
        L.data.shadow_soft_size = 0.4
    BLv = Vector((*SITE["BL"], 0))
    ang = math.atan2(right.y, right.x)
    for k, (off, size) in enumerate(((Vector((0, 0, 0)), (22, 10, 6.5)), (Vector((0, 0, 0)), (12, 9, 9)))):
        ec = BLv + right * (14 + 20 * k) - view_c * (14 + 8 * k)
        box_mesh(ec.x, ec.y, size[2] / 2, size[0], size[1], size[2], M["clad"], f"Equipment{k}", rot_z=ang)
        for i in range(4):
            wp = ec + right * (-size[0] / 2 + 3 + i * (size[0] - 6) / 3) + view_c * (size[1] / 2 + 0.06)
            box_mesh(wp.x, wp.y, 2.4, 1.8, 0.08, 1.4, M["window"], "Win", rot_z=ang)
    dish = BLv + right * 34 - view_c * 22 + Vector((0, 0, 10.0))
    sphere(dish, 1.6, M["steel"], "Dish")
    for i in range(80):
        a_ = math.radians(-40 + i * 1.6)
        rr = 160 + (i * 37) % 50
        q = (rr * math.cos(a_), rr * math.sin(a_))
        bpy.ops.mesh.primitive_cone_add(radius1=3.5, depth=12 + (i * 13) % 7, location=(q[0], q[1], 6.0))
        bpy.context.active_object.data.materials.append(M["tree"])
    global FACES
    FACES = face_defs
    return At, Lt, Rt


def world_and_lights(shot):
    w = bpy.data.worlds.new("Night")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    if shot == "night":
        ramp.color_ramp.elements[0].position = 0.5
        ramp.color_ramp.elements[0].color = (0.012, 0.02, 0.075, 1)
        ramp.color_ramp.elements[1].position = 0.75
        ramp.color_ramp.elements[1].color = (0.0015, 0.003, 0.018, 1)
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 700
        sr = nt.nodes.new("ShaderNodeValToRGB")
        sr.color_ramp.elements[0].position = 0.0
        sr.color_ramp.elements[0].color = (6, 6, 7, 1)
        sr.color_ramp.elements[1].position = 0.025
        sr.color_ramp.elements[1].color = (0, 0, 0, 1)
        add = nt.nodes.new("ShaderNodeMix")
        add.data_type = "RGBA"
        add.blend_type = "ADD"
        add.inputs["Factor"].default_value = 1.0
        nt.links.new(tc.outputs["Generated"], vor.inputs["Vector"])
        nt.links.new(vor.outputs["Distance"], sr.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], add.inputs[6])
        nt.links.new(sr.outputs["Color"], add.inputs[7])
        nt.links.new(add.outputs[2], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 1.0
        # floodlights washing the faces from the ground, cool moonlight
        flood = []
        for n, t, base0, wface in FACES:
            fc = Vector((base0[0] + t[0] * wface / 2, base0[1] + t[1] * wface / 2, 0))
            nn, tt = Vector((n[0], n[1], 0)), Vector((t[0], t[1], 0))
            for o in (-9, 9):
                flood.append((tuple(fc + nn * 11 + tt * o + Vector((0, 0, 0.5))), tuple(fc + tt * o * 0.3 + Vector((0, 0, 17)))))
        for p, tgt in flood:
            bpy.ops.object.light_add(type="SPOT", location=p)
            L = bpy.context.active_object
            L.data.energy = 9000
            L.data.spot_size = math.radians(70)
            L.data.spot_blend = 0.6
            L.data.color = (0.95, 0.93, 1.0)
            L.rotation_mode = "QUATERNION"
            L.rotation_quaternion = (Vector(tgt) - Vector(p)).to_track_quat("-Z", "Y")
        bpy.ops.object.light_add(type="SUN", rotation=(math.radians(60), 0, math.radians(200)))
        bpy.context.active_object.data.energy = 0.05
        bpy.context.active_object.data.color = (0.6, 0.7, 1.0)
    else:
        ramp.color_ramp.elements[0].position = 0.5
        ramp.color_ramp.elements[0].color = (0.85, 0.55, 0.4, 1)
        ramp.color_ramp.elements[1].position = 0.8
        ramp.color_ramp.elements[1].color = (0.12, 0.2, 0.42, 1)
        nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 1.3
        bpy.ops.object.light_add(type="SUN", rotation=(math.radians(78), 0, math.radians(235)))
        bpy.context.active_object.data.energy = 2.2
        bpy.context.active_object.data.color = (1.0, 0.78, 0.6)
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def camera(shot):
    if shot == "night":
        loc, tgt, lens = (-55.5, -32.1, 1.3), (-12.0, -29.6, 14.0), 15
    else:
        loc, tgt, lens = (-140.0, -20.0, 70.0), (-6.0, -20.0, 10.0), 32
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object
    cam.data.lens = lens
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y")
    bpy.context.scene.camera = cam


def render(shot):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.cycles.device = "CPU"          # laptop GPU driver too old for Cycles kernels
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    sc.render.resolution_percentage = int(ARGS[2]) if len(ARGS) > 2 else 100
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = 0.6 if shot == "night" else 0.0
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 90
    sc.render.filepath = str(OUT / f"sentinel_{shot}.jpg")
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "sentinel_site.blend"))


if __name__ == "__main__":
    reset()
    build()
    world_and_lights(SHOT)
    camera(SHOT)
    render(SHOT)
    print("rendered", SHOT)
