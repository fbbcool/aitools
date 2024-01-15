env_inst() {
    pip install -r $ENV_HOME/requirements.txt
    #pip install -r $ENV_HOME/requirements_traingen.txt
    #pip install -r $ENV_HOME/requirements_gen.txt
    #env_pool_inst https://drive.google.com/file/d/1wdS5ULSgHV6KaaH9y6vHZY_-O6m5AXpB/view?usp=sharing
    python3 $ENV_HOME/src/script/comfyui.py
}

#export ENV_POOLS=$ENV_HOME/pools
#export ENV_TRAINS=$ENV_HOME/trains
#export ENV_MODELS=$ENV_HOME/models
#export ENV_TMP=$ENV_HOME/tmp
#export ENV_TMP_POOL_TAR=$ENV_TMP/pool.tar
export ENV_DIR_REMOTE_VENV=/ComfyUI

#mkdir -p $ENV_POOLS
#mkdir -p $ENV_TRAINS
#mkdir -p $ENV_MODELS
#mkdir -p $ENV_TMP

source $ENV_DIR_REMOTE_VENV/venv/bin/activate