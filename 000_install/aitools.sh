#!/bin/sh
export REPOS_AIT='https://github.com/fbbcool/aitools.git'
export REPOS_TRAINER='https://github.com/tdrussell/diffusion-pipe'
#export REPOS_TRAINER='https://github.com/fbbcool/diffusion-pipe'
export WORKSPACE='/workspace'
export HOME_TRAINER=$WORKSPACE/diffusion-pipe
export HOME_AIT=$WORKSPACE/aitools
export CONF_AIT=$HOME_AIT/conf
export PYTHONPATH=$HOME_AIT/src

___train_install_aitools() {
  git clone $REPOS_AIT $HOME_AIT
  pip install -r $HOME_AIT/requirements_remote.txt
}
___train_install_trainer() {
  rm -rf $HOME_TRAINER
  git clone $REPOS_TRAINER $HOME_TRAINER
  cd $HOME_TRAINER
  git submodule update --init --recursive

  pip install --no-build-isolation flash-attn>=2.8.3
  pip install -r requirements.txt

  pip uninstall diffusers
  yes | pip install git+https://github.com/huggingface/diffusers
}
train_install() {
  ___train_install_aitools
  ___train_install_trainer
}
train_prepare() {
  python $HOME_AIT/script/train_prepare.py
  cp $WORKSPACE/train/train.sh $HOME_TRAINER
}
train_run() {
  train_prepare
  cd $HOME_TRAINER
  ./train.sh
}
train_clean() {
  rm -rf $WORKSPACE/train
}

alias t='vi $HOME_AIT/script/train_prepare.py'

ait_pull() {
  echo "update aitools ..."
  git -C $HOME_AIT pull
}

