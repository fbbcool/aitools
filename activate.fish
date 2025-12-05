function ait_update
    echo "update aitools ..."
    git -C $HOME_AIT pull
end

function ait_setup_comfyui
    ait_update
    python3 $HOME_AIT/script/ainstall_comfyui.py $HOME_COMFY comfyui
end

function ait_setup_qwen
    ait_update
    python3 $HOME_AIT/script/ainstall_comfyui.py $HOME_COMFY qwen:image
end

function ait_setup_qwen_edit
    ait_update
    python3 $HOME_AIT/script/ainstall_comfyui.py $HOME_COMFY qwen:edit
end

function ait_setup_wan22
    ait_update
    python3 $HOME_AIT/script/ainstall_comfyui.py $HOME_COMFY wan22:t2v
end

function ait_setup_wan22_i2v
    ait_update
    python3 $HOME_AIT/script/ainstall_comfyui.py $HOME_COMFY wan22:i2v
end

function ait_setup_zimage_turbo
    ait_update
    python3 $HOME_AIT/script/ainstall_comfyui.py $HOME_COMFY zimage:turbo
end

function ait_setup_zimage_base
    ait_update
    python3 $HOME_AIT/script/ainstall_comfyui.py $HOME_COMFY zimage:base
end

function ait_setup_zimage_edit
    ait_update
    python3 $HOME_AIT/script/ainstall_comfyui.py $HOME_COMFY zimage:edit
end

#function ait_wan21 () {
#  ___install
#  ___setup_wan21
#  ___hook
#}

function ait_clean_gen
    rm -rf $HOME_COMFY/output/video
    rm -rf $HOME_COMFY/temp/*
end

function ait_prompt_clipspace
    python3 $HOME_AIT/script/img_prompt.py (wl-paste) | wl-copy
    echo (wl-paste)
end
