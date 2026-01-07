#!/bin/sh
export REPOS_AIT='https://github.com/fbbcool/aitools.git'
export WORKSPACE='/workspace'
export HOME_AIT=$WORKSPACE/aitools
export CONF_AIT=$HOME_AIT/conf
export PYTHONPATH=$HOME_AIT/src

___install() {
  git clone $REPOS_AIT $HOME_AIT
  pip install -r $HOME_AIT/requirements_remote.txt
}
___update() {
  echo "update aitools ..."
  git -C $HOME_AIT pull
}
