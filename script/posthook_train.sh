git clone https://github.com/tdrussell/diffusion-pipe /workspace/diffusion-pipe
cd /workspace/diffusion-pipe
git submodule update --init --recursive
cp /workspace/train/train.sh /workspace/diffusion-pipe

echo -n " !!! !!!!!!!!!!!!!!!!!!!!!!!!!! !!!"
echo -n " !!! update to flash-attn 2.8.3 !!!"
echo -n " !!! !!!!!!!!!!!!!!!!!!!!!!!!!! !!!"
pip install -r requirements.txt --upgrade --no-build-isolation