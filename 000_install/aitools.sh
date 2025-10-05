export ENV_REPOS='https://github.com/fbbcool/aitools.git'
export ENV_WORKSPACE='/workspace'
export ENV_HOME=$ENV_WORKSPACE/___aitools
export ENV_POST_HOOK=$ENV_WORKSPACE/post_install_hook.sh
export PYTHONPATH=$ENV_HOME/src

___install() {
    rm -rf $ENV_HOME
    git clone $ENV_REPOS $ENV_HOME
    #pip install -r $ENV_HOME/requirements.txt
    pip install -r $ENV_HOME/requirements_remote.txt
}
___hook () {
    if [ -x $ENV_POST_HOOK ]; then
        $ENV_POST_HOOK
    fi
}
___setup_qwen () {
    python3 $ENV_HOME/script/vastai.py "qwen"
}

___setup_qwen_edit () {
    python3 $ENV_HOME/script/vastai.py "qwen_edit"
}

___setup_wan21 () {
    python3 $ENV_HOME/script/vastai.py "wan21"
}

___setup_wan22 () {
    python3 $ENV_HOME/script/vastai.py "wan22"
}

___current () {
    python3 $ENV_HOME/script/vastai.py "current"
}

___wan21 () {
    ___install
    ___setup_wan21
    ___hook
}
___wan22 () {
    ___install
    ___setup_wan22
    ___hook
}
___qwen () {
    ___install
    ___setup_qwen
    ___hook
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

___clean_gen ()
{
    rm -rf /workspace/ComfyUI/output/video
    rm -rf /workspace/ComfyUI/temp/
}
