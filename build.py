import subprocess
import os
import sys

def build():
    try:
        import customtkinter
        import fido2
    except ImportError:
        print("Error: required build dependencies are not installed. Please install requirements first.")
        sys.exit(1)

    # Get the path to customtkinter
    ctk_path = os.path.dirname(customtkinter.__file__)

    # On Windows, os.pathsep is ';', on Linux/macOS it's ':'
    # PyInstaller add-data format: SOURCE;DEST or SOURCE:DEST
    add_data_path = f"{ctk_path}{os.pathsep}customtkinter"
    fido2_psl_path = os.path.join(os.path.dirname(fido2.__file__), "public_suffix_list.dat")
    fido2_add_data_path = f"{fido2_psl_path}{os.pathsep}fido2"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        f"--add-data={add_data_path}",
        f"--add-data={fido2_add_data_path}",
        "--name", "iCloudSynoSync",
        "src/main.py"
    ]

    print(f"Building with command: {' '.join(command)}")
    
    try:
        subprocess.run(command, check=True)
        print("Build successful! Check the 'dist' folder.")
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
    except FileNotFoundError:
        print("Error: pyinstaller not found. Please install it with 'pip install pyinstaller'.")

if __name__ == "__main__":
    build()
