env_up() {
    source $ENV_HOME/$ENV_DIR/bin/activate
    if [ -n "${PYTHONPATH+1}" ]; then
        export PYTHONPATH
    fi
    export PYTHONPATH_OLD=$PYTHONPATH
    export PYTHONPATH=$ENV_HOME/src:$PYTHONPATH_OLD
}
env_down() {
    export PYTHONPATH=$PYTHONPATH_OLD
    unset PYTHONPATH_OLD
    deactivate
}
env_up() {
    pyhton -m venv $ENV_HOME/$ENV_DIR
    source $ENV_HOME/$ENV_DIR/bin/activate
    pip install -r $ENV_HOME/requirements.txt
}

export ENV_HOME=`pwd`
export ENV_DIR="venv"