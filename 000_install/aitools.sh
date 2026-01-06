#!/bin/sh
export AIT_REPOS='https://github.com/fbbcool/aitools.git'
export WORKSPACE='/workspace'
export AIT_HOME=$WORKSPACE/aitools
export PYTHONPATH=$AIT_HOME/src

___install() {
  git clone $AIT_REPOS $AIT_HOME
  pip install -r $AIT_HOME/requirements_remote.txt
}
___update() {
  echo "update aitools ..."
  git -C $AIT_HOME pull
}
