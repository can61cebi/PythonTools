import os
import sys

# --- Directories to exclude from the search ---
# Use a set for faster lookups
EXCLUDE_DIRS = {
    'node_modules',
    '.nuxt',
    '.output',
    '.git',  # Good practice to exclude git directory
    '.vscode', # Often contains settings, not source code
    'dist', # Common build output directory name
    '.cache' # Common cache directory name
}
# --- ---

def find_files_with_extensions(directory, extensions, exclude_dirs):
    """
    Recursively find all files with the given extensions in the directory
    and its subdirectories, excluding specified directory names.
    """
    matched_files = []

    for root, dirs, files in os.walk(directory, topdown=True):
        # Modify the list of directories *in place* to prevent os.walk
        # from descending into excluded directories.
        # We iterate over a copy of dirs[:] because we're modifying it.
        dirs[:] = [d for d in dirs if d not in exclude_dirs]

        for file in files:
            # Check if the *current* root directory itself should be skipped
            # (e.g., if the starting directory was node_modules)
            # This check might be slightly redundant given the dirs[:] modification
            # but adds an extra layer of safety.
            if any(excluded in root.split(os.sep) for excluded in exclude_dirs):
                 continue # Skip files in already excluded parent paths

            if any(file.endswith(ext) for ext in extensions):
                matched_files.append(os.path.join(root, file))

    return sorted(matched_files)  # Sort files for consistent output

def create_combined_file(files, output_file):
    """
    Create a single file with the content of all the found files.
    """
    print(f"Birleştirilmiş dosyaya {len(files)} adet dosya yazılıyor...")
    with open(output_file, 'w', encoding='utf-8', errors='replace') as out_f: # Use errors='replace' for robustness
        for i, file_path in enumerate(files):
            # Optional: Print progress
            # print(f"  [{i+1}/{len(files)}] {file_path}")
            out_f.write(f"--- File Start: {file_path} ---\n")
            # out_f.write("=" * 80 + "\n") # Keep or remove separator as you prefer

            try:
                # Try to read as text with UTF-8 encoding first
                with open(file_path, 'r', encoding='utf-8') as in_f:
                    content = in_f.read()
                    out_f.write(content)
            except UnicodeDecodeError:
                # If UTF-8 fails, try with Latin-1 (or another common encoding if known)
                try:
                    with open(file_path, 'r', encoding='latin-1') as in_f:
                        content = in_f.read()
                        out_f.write(f"--- Note: Read with Latin-1 encoding (UTF-8 failed) ---\n")
                        out_f.write(content)
                except Exception as e:
                    out_f.write(f"--- Error reading file (Latin-1 fallback failed): {str(e)} ---\n")
            except Exception as e:
                 # Catch other potential errors like permission issues
                out_f.write(f"--- Error reading file: {str(e)} ---\n")

            out_f.write(f"\n--- File End: {file_path} ---\n\n") # Clearer end marker

def main():
    # Default values
    directory = os.getcwd()
    output_file = "birlestirilmis_kaynak_dosyalari.txt" # More descriptive name

    # Parse command line arguments
    if len(sys.argv) > 1:
        directory = sys.argv[1]

    if len(sys.argv) > 2:
        output_file = sys.argv[2]

    extensions = ['.env', '.vue', '.ts', '.js', '.sh', '.json', '.toml', '.rs']

    print(f"Searching for files with extensions ({', '.join(extensions)})")
    print(f"  in directory: {directory}")
    print(f"  excluding folders: {', '.join(sorted(list(EXCLUDE_DIRS)))}") # Show excluded folders

    # Check if the directory exists
    if not os.path.isdir(directory):
        print(f"Hata: '{directory}' dizini bulunamadı veya bir dizin değil.")
        sys.exit(1)

    # Pass the exclude_dirs set to the find function
    files = find_files_with_extensions(directory, extensions, EXCLUDE_DIRS)
    print(f"{len(files)} matching files found (after exclusions).")

    if not files:
        print("No matching files found after applying exclusions.")
        sys.exit(0)

    try:
        create_combined_file(files, output_file)
        print(f"Combined file created successfully: {output_file}")
    except Exception as e:
        print(f"Error creating the combined file: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()