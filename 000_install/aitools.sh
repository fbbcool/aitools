export ENV_REPOS='https://github.com/fbbcool/aitools.git'
export ENV_PWD=`pwd`
export ENV_HOME=$ENV_PWD/___aitools

___train() {
    rm -rf $ENV_HOME
    git clone $ENV_REPOS $ENV_HOME
    source $ENV_HOME/env_aitools/env_train.sh
    env_inst
}
___gen () {
    rm -rf $ENV_HOME
    git clone $ENV_REPOS $ENV_HOME
    source $ENV_HOME/env_aitools/env_gen.sh
    env_inst
}
___comfy () {
    rm -rf $ENV_HOME
    git clone $ENV_REPOS $ENV_HOME
    source $ENV_HOME/env_aitools/env_comfy.sh
    env_inst
}

___sd15 () {
    git -C $ENV_HOME pull
    comfyui_sd15
}

___sdxl () {
    git -C $ENV_HOME pull
    comfyui_sdxl
}

___sdall () {
    git -C $ENV_HOME pull
    comfyui_sdall
}

