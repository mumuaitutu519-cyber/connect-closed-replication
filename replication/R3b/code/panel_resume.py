from common import *
import subprocess
if __name__=='__main__':
 subprocess.run([sys.executable,str(R/'code/pooled_bounded.py')],check=True)
 subprocess.run([sys.executable,str(R/'code/panel.py'),'panel'],check=True)
