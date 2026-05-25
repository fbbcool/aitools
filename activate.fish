set -xg AIT_WORKSPACE $WORKSPACE/aitools
set -xg AIT_TMP $HOME/Downloads/000_tmp
set -xg AIDB_SCENE_DEFAULT 0000
set -xg AIDB_SCENE_CONFIG default

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

function ait_setup_ltx
    ait_update
    python3 $HOME_AIT/script/ainstall_comfyui.py $HOME_COMFY ltx:23
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
    set output (python3 $HOME_AIT/script/img_caption.py (wl-paste) $argv)
    set out2 (echo $output | grep -o '<caption>.*</caption>' | sed 's/\(<caption>\|<\/caption>\)//g')
    echo $out2 | wl-copy
    echo -n (wl-paste)
end

function ait_caption
    set img (wl-paste)
    if not test -f "$img"
        echo "[ait_caption] not a file: $img"
        return
    end
    set ext (string lower (string match -r '\.[^.]+$' -- "$img"))
    switch $ext
        case .png .webp .jpg .jpeg .gif
        case '*'
            echo "[ait_caption] not an image: $img"
            return
    end
    ait_tmp_clipspace
    set bodies (python3 -c "
from ait.caption.skin import SkinRegistry
sk = SkinRegistry().get('1xlasm')
print('\n'.join(sorted(l.split('.')[-1] for l, g in sk.label_to_group.items() if g == 'primary.attribute')))
")
    echo -n "body? (0) none"
    set i 1
    for b in $bodies
        echo -n "  ($i) $b"
        set i (math $i + 1)
    end
    echo ""
    read -P "> " -n 1 choice
    set body ""
    if string match -qr '^[1-9][0-9]*$' -- $choice
        if test $choice -ge 1 -a $choice -le (count $bodies)
            set body $bodies[$choice]
        end
    end

    read -P "penis? [enter=yes, any other key=no] > " -n 1 pchoice
    set penis 0
    if test -z "$pchoice"
        set penis 1
    end

    read -P "hint? (enter=none) > " hint

    ait_img_caption_clipspace "$body" "$penis" "$hint"
end

function ait_server_joy
    set skin $argv[1]
    test -z "$skin"; and set skin 1xlasm

    set running (python3 -c "from ait.caption import joy_client; print('1' if joy_client.is_running() else '0')")
    if test "$running" = 1
        set current_skin (python3 -c "from ait.caption import joy_client; print(joy_client.status().get('skin') or '')")
        set msg "joy_server is running with skin=$current_skin; stop it?"
        set action stop
    else
        set msg "joy_server is stopped; start it with skin=$skin?"
        set action start
    end

    read -P "$msg [enter=yes, any other key=no] > " -n 1 choice
    if test -n "$choice"
        echo "no change"
        return
    end
    if test "$action" = start
        python3 -c "from ait.caption import joy_client; joy_client.ensure_running(skin='$skin'); print(joy_client.status())"
    else
        python3 -c "from ait.caption import joy_client; ok = joy_client.shutdown(); print('stopped' if ok else 'shutdown timeout')"
    end
end

function ait_prompt
    ait_tmp_clipspace
    ait_img_prompt_clipspace
end

function ait_tmp_clipspace
    set input (wl-paste)
    echo $input
    cp $input $AIT_TMP
end

function ait_tmp_clean
    rm $AIT_TMP/*.png
end

function aidb_scene_path_clipspace
    set output (python3 $HOME_AIT/script/scene_url_from_reg_file.py (wl-paste))
    wl-copy (string trim $output)
end

function aidb_scene
    python3 $HOME_AIT/script/aidb_scene.py $argv
end
function aidb_scene_default
    set -xg AIDB_SCENE_DEFAULT $argv
end
function aidb_scene_config
    set -xg AIDB_SCENE_CONFIG $argv
end

function comfy_clean_gen
    rm -rf $HOME_COMFY/output/video
    rm -f $HOME_COMFY/output *.mp4 *.png
    rm -rf $HOME_COMFY/temp/*
end

function comfy_save_latest_vid
    set dir $HOME_COMFY/output/video/save
    lslast 2 $dir | xargs -t -i cp $dir/{} $HOME/Downloads
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
