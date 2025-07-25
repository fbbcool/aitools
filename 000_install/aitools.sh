export ENV_REPOS='https://github.com/fbbcool/aitools.git'
export ENV_PWD=`pwd`
export ENV_HOME=$ENV_PWD/___aitools
export PYTHONPATH=$ENV_HOME/src

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


___flux () {
    git -C $ENV_HOME pull
    comfyui_flux
}

___flux_refine () {
    git -C $ENV_HOME pull
    comfyui_flux_refine
}

___hidream () {
    git -C $ENV_HOME pull
    comfyui_hidream
}

___fluxgym () {
    git -C $ENV_HOME pull
    comfyui_fluxgym
}

___kohyass_flux () {
    git -C $ENV_HOME pull
    comfyui_kohyass_flux
}

___kohyass_sdxl () {
    git -C $ENV_HOME pull
    comfyui_kohyass_sdxl
}

___current () {
    git -C $ENV_HOME pull
    comfyui_current
}

