#!/bin/sh
export REPOS_AIT='https://github.com/fbbcool/aitools.git'
#export REPOS_TRAINER='https://github.com/tdrussell/diffusion-pipe'
export REPOS_TRAINER='https://github.com/fbbcool/diffusion-pipe'
export REPOS_TRAINER_BRANCH='feature-xlasm-frozen'
export WORKSPACE='/workspace'
export DIR_TRAIN=$WORKSPACE/train
export HOME_TRAINER=$WORKSPACE/diffusion-pipe
export HOME_AIT=$WORKSPACE/aitools
export CONF_AIT=$HOME_AIT/conf
export PYTHONPATH=$HOME_AIT/src

___train_install_aitools() {
  git clone $REPOS_AIT $HOME_AIT
  pip install -r $HOME_AIT/requirements_remote.txt
}
___train_install_flash_attn() {
  # Pull the prebuilt flash-attn wheel matching the active torch/cuda/python/cxx-abi
  # combo. Wheels live on GitHub Releases (not PyPI), so a direct URL pull avoids
  # the ~30 min source compile. Falls back to source compile if no matching wheel
  # exists for the detected combo. Override version via FLASH_ATTN_VER env var.
  local ver="${FLASH_ATTN_VER:-2.8.3}"
  local cuda torch_ver py_ver cxx_abi wheel
  cuda=$(python3 -c 'import torch; v=torch.version.cuda or ""; print(v.split(".")[0])')
  torch_ver=$(python3 -c 'import torch; v=torch.__version__.split("+")[0].split("."); print(f"{v[0]}.{v[1]}")')
  py_ver=$(python3 -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')
  cxx_abi=$(python3 -c 'import torch; print("TRUE" if torch.compiled_with_cxx11_abi() else "FALSE")')
  wheel="https://github.com/Dao-AILab/flash-attention/releases/download/v${ver}/flash_attn-${ver}+cu${cuda}torch${torch_ver}cxx11abi${cxx_abi}-${py_ver}-${py_ver}-linux_x86_64.whl"

  echo "trying flash-attn wheel: $wheel"
  if pip install "$wheel"; then
    echo "flash-attn wheel installed ✓"
  else
    echo "wheel not available (cu${cuda}/torch${torch_ver}/${py_ver}/cxx11abi=${cxx_abi}); falling back to source compile"
    pip install --no-build-isolation "flash-attn==${ver}"
  fi
}
___train_install_trainer() {
  rm -rf $HOME_TRAINER
  git clone ${REPOS_TRAINER_BRANCH:+--branch $REPOS_TRAINER_BRANCH} $REPOS_TRAINER $HOME_TRAINER
  cd $HOME_TRAINER
  git submodule update --init --recursive

  ___train_install_flash_attn
  pip install -r requirements.txt

  #pip uninstall diffusers
  #yes | pip install git+https://github.com/huggingface/diffusers
  pip install -U "diffusers==0.35.*"
}
train_install() {
  ___train_install_aitools
  ___train_install_trainer
}
train_prepare() {
  python3 $HOME_AIT/script/train_prepare.py
  cp $DIR_TRAIN/train.sh $HOME_TRAINER
}
train_run() {
  train_prepare
  cd $HOME_TRAINER
  ./train.sh
}
clean_train() {
  rm -rf $DIR_TRAIN
}

clean_dataset() {
  rm -rf $DIR_TRAIN/dataset
}

clean_output() {
  rm -rf $DIR_TRAIN/output
}


alias t='vi $HOME_AIT/script/train_prepare.py'

ait_pull() {
  echo "update aitools ..."
  git -C $HOME_AIT pull
}

