import subprocess
import sys

with open("requirements.txt", "r") as f:
    packages = f.readlines()

for package in packages:
    package = package.strip()
    if package and not package.startswith('#'):
        try:
            print(f"Attempting to install: {package}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"Successfully installed: {package}\n")
        except subprocess.CalledProcessError as e:
            print(f"FAILED to install: {package}")
            print(f"Error details: {e}\n")
            # Continue to the next package in the list
