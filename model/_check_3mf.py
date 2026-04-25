import zipfile, re, glob, os
for f in sorted(glob.glob('model/out/*.3mf')):
    with zipfile.ZipFile(f) as z:
        x = z.read('3D/3dmodel.model').decode('utf-8', 'ignore')
    objs = re.findall(r'<object\s+id="(\d+)"[^>]*type="model"', x)
    # count <mesh> inside each object (unique meshes = separate solids)
    meshes = len(re.findall(r'<mesh>', x))
    comps  = len(re.findall(r'<component ', x))
    print(f'{os.path.basename(f):35s} objects(type=model)={len(objs):2d}  meshes={meshes:2d}  components={comps}')
