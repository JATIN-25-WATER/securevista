# Torch and Cuda documentation for this project main machine.
This document aims to detail any specfic version of softwares, packages, and drivers in the event any compatibility issues arises.

## My GPU (RTX-3060 Mobile) initial stats:
command: ```nvidia-smi```  
ouput:   
Sat Nov 25 13:53:52 2023  
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 512.95       Driver Version: 512.95       CUDA Version: 11.6     |
|-------------------------------+----------------------+----------------------+
| GPU  Name            TCC/WDDM | Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|                               |                      |               MIG M. |
|===============================+======================+======================|
|   0  NVIDIA GeForce ... WDDM  | 00000000:01:00.0  On |                  N/A |
| N/A   52C    P8    14W /  N/A |    362MiB /  6144MiB |     38%      Default |
|                               |                      |                  N/A |
+-------------------------------+----------------------+----------------------+

## Update from CUDA 11.6 to 12.1  
CUDA 12.1: https://developer.nvidia.com/cuda-12-1-0-download-archive?target_os=Windows&target_arch=x86_64&target_version=11&target_type=exe_local  
PyTorch install: ```pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121```   

Sat Nov 25 16:33:35 2023  
+---------------------------------------------------------------------------------------+
| NVIDIA-SMI 531.14                 Driver Version: 531.14       CUDA Version: 12.1     |
|-----------------------------------------+----------------------+----------------------+
| GPU  Name                      TCC/WDDM | Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp  Perf            Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
|                                         |                      |               MIG M. |
|=========================================+======================+======================|
|   0  NVIDIA GeForce RTX 3060 L...  WDDM | 00000000:01:00.0  On |                  N/A |
| N/A   49C    P8               12W /  N/A|    300MiB /  6144MiB |     19%      Default |
|                                         |                      |                  N/A |
+-----------------------------------------+----------------------+----------------------+  
If "NotImplementedError: Could not run 'torchvision::nms'" error arises, see below.  


## Fixed pip install
command: ```python -m pip install --upgrade pip```  

## Generated requirements.txt file
command: ```pip freeze > requirements.txt```  

## ERROR: NotImplementedError: Could not run 'torchvision::nms'
This is caused by using torchvision without CUDA while having everything else with CUDA.   
Fix:   
1. First do ``````pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121``````
2. Then ```pip install torchvision==0.16.0+cu121 -f https://download.pytorch.org/whl/torch_stable.html```  
Note: For some reason the first command does not install torchvision with CUDA. Second command will fix the issue.  
Source: https://discuss.pytorch.org/t/notimplementederror-could-not-run-torchvision-nms-with-arguments-from-the-cuda-backend-this-could-be-because-the-operator-doesnt-exist-for-this-backend/132352

