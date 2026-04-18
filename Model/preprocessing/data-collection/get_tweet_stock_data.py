import kagglehub

# Download latest version
path = kagglehub.dataset_download("williamtage/trace-acl18")

print("Path to dataset files:", path)
