import subprocess
import os
import sys

def build():
    try:
        import customtkinter
    except ImportError:
        print("Error: customtkinter is not installed. Please install it first.")
        sys.exit(1)

    # Get the path to customtkinter
    ctk_path = os.path.dirname(customtkinter.__file__)

    # On Windows, os.pathsep is ';', on Linux/macOS it's ':'
    # PyInstaller add-data format: SOURCE;DEST or SOURCE:DEST
    add_data_path = f"{ctk_path}{os.pathsep}customtkinter"

    command = [
        "pyinstaller",
        "--onefile",
        "--windowed",
        f"--add-data={add_data_path}",
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
