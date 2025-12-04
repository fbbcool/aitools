import sys
from ait.install import AInstaller

if __name__ == '__main__':
    base_dir = sys.argv[1]
    group = sys.argv[2]
    AInstaller(base_dir, group=group, method='comfyui')
