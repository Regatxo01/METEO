import pathlib, subprocess, sys, shutil
base=pathlib.Path(__file__).resolve().parent
subprocess.run([sys.executable,str(base/'alertas_cp.py')],cwd=base,check=True)
shutil.copyfile(base/'alertas_edificios.html',base/'index.html')
print('index.html actualizado correctamente')
