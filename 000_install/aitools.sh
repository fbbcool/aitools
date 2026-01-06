#!/bin/sh
export REPOS_AIT='https://github.com/fbbcool/aitools.git'
export WORKSPACE='/workspace'
export HOME_AIT=$WORKSPACE/aitools
export CONF_AIT=$HOME_AIT/conf
export PYTHONPATH=$HOME_AIT/src

___install() {
  git clone $AIT_REPOS $AIT_HOME
  pip install -r $AIT_HOME/requirements_remote.txt
}
___update() {
  echo "update aitools ..."
  git -C $AIT_HOME pull
}
