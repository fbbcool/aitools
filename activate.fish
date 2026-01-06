set -xg AIT_TMP $HOME/Downloads/000_tmp/
set -xg WORKSPACE $HOME/Workspace

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

function ait_setup_train_zimage_turbo
    ait_update
    python3 $HOME_AIT/script/ainstall_diffpipe.py $WORKSPACE train_zimage:turbo
end

#function ait_wan21 () {
#  ___install
#  ___setup_wan21
#  ___hook
#}

function ait_img_prompt_clipspace
    echo (wl-paste)
    python3 $HOME_AIT/script/img_prompt.py (wl-paste) | wl-copy
    echo (wl-paste)
end

function ait_img_caption_clipspace
    echo (wl-paste)
    #python3 $HOME_AIT/script/img_caption.py (wl-paste) | sed 's/\(<prompt>\|<\/prompt>\)//g' | wl-copy
    set output (python3 $HOME_AIT/script/img_caption.py (wl-paste))
    set out2 (echo $output | grep -o '<prompt>.*</prompt>' | sed 's/\(<prompt>\|<\/prompt>\)//g')
    echo $out2 | wl-copy
    echo -n (wl-paste)
end

function ait_caption
    ait_tmp_clipspace
    ait_img_caption_clipspace
end

function ait_tmp_clipspace
    set input (wl-paste)
    echo $input
    cp $input $AIT_TMP
end

function ait_tmp_clean
    rm $AIT_TMP/*.png
end

function comfy_clean_gen
    rm -rf $HOME_COMFY/output/video
    rm -f $HOME_COMFY/output *.mp4 *.png
    rm -rf $HOME_COMFY/temp/*
end

function comfy_save_latest_vid_prores
    set dir $HOME_COMFY/output/video/prores
    lslast 2 $dir | xargs -t -i cp $dir/{} $HOME/Downloads
end

function comfy_save_latest_vid_upscale
    set dir $HOME_COMFY/output/video/upscale
    lslast 2 $dir | xargs -t -i cp $dir/{} $HOME/Downloads
end

function comfy_pip_install
    uv pip install -r $HOME_COMFY/requirements_ainstall.txt --no-build-isolation
end
