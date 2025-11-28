function ait_update
    echo "update aitools ..."
    git -C $HOME_AIT pull
end

function ait_setup_qwen
    ait_update
    python3 $HOME_AIT/script/vastai.py qwen
end

function ait_setup_qwen_edit
    ait_update
    python3 $HOME_AIT/script/vastai.py qwen_edit
end

function ait_setup_wan21
    ait_update
    python3 $HOME_AIT/script/vastai.py wan21
end

function ait_setup_wan22
    ait_update
    python3 $HOME_AIT/script/vastai.py wan22
end

function ait_setup_wan22_i2v
    ait_update
    python3 $HOME_AIT/script/vastai.py wan22_i2v
end

function ait_current
    ait_update
    python3 $HOME_AIT/script/vastai.py current
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
