git clone https://github.com/tdrussell/diffusion-pipe /workspace/diffusion-pipe
cd /workspace/diffusion-pipe
git submodule update --init --recursive
echo -n " !!! update to flash-attn 2.8.3 !!!"
pip install -r requirements.txt --upgrade --no-build-isolation
cp /workspace/train/train.sh /workspace/diffusion-pipe