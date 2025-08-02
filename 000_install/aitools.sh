export ENV_REPOS='https://github.com/fbbcool/aitools.git'
export ENV_WORKSPACE='/workspace'
export ENV_HOME=$ENV_WORKSPACE/___aitools
export ENV_POST_HOOK=$ENV_WORKSPACE/post_install_hook.sh
export PYTHONPATH=$ENV_HOME/src

___install() {
    rm -rf $ENV_HOME
    git clone $ENV_REPOS $ENV_HOME
    pip install -r $ENV_HOME/requirements.txt
    #pip install -r $ENV_HOME/requirements_remote.txt
}
zzzenv_post_install_hook () {
    if [ -x $ENV_POST_HOOK ]; then
        $ENV_POST_HOOK
    fi
}
___current () {
    zzzenv_post_install_hook
    python3 $ENV_HOME/script/vastai.py "current"
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
