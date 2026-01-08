#!/bin/sh
export REPOS_AIT='https://github.com/fbbcool/aitools.git'
export WORKSPACE='/workspace'
export HOME_AIT=$WORKSPACE/aitools
export CONF_AIT=$HOME_AIT/conf
export PYTHONPATH=$HOME_AIT/src

train_install() {
  rm -rf $WORKSPACE/diffusion-pipe
  git clone https://github.com/tdrussell/diffusion-pipe $WORKSPACE/diffusion-pipe
  #git clone https://github.com/fbbcool/diffusion-pipe $WORKSPACE/diffusion-pipe
  cd $WORKSPACE/diffusion-pipe
  git submodule update --init --recursive

  pip install --no-build-isolation flash-attn>=2.8.3
  pip install -r requirements.txt

  pip uninstall diffusers
  pip install git+https://github.com/huggingface/diffusers

  git -C $HOME_AIT pull
}
train_prepare() {
  python $HOME_AIT/script/train_prepare.py
  cp $WORKSPACE/train/train.sh $WORKSPACE/diffusion-pipe
}
train_run() {
  train_prepare
  cd $WORKSPACE/diffusion-pipe
  ./train.sh
}

alias t='vi $HOME_AIT/script/train_prepare.py'

___install() {
  git clone $REPOS_AIT $HOME_AIT
  pip install -r $HOME_AIT/requirements_remote.txt
  train_install
}
___update() {
  echo "update aitools ..."
  git -C $HOME_AIT pull
}

