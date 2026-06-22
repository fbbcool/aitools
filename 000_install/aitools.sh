#!/bin/sh
export REPOS_AIT='https://github.com/fbbcool/aitools.git'
#export REPOS_TRAINER='https://github.com/tdrussell/diffusion-pipe'
export REPOS_TRAINER='https://github.com/fbbcool/diffusion-pipe'
export REPOS_TRAINER_BRANCH='feature-xlasm-frozen'
export WORKSPACE='/workspace'
export DIR_TRAIN=$WORKSPACE/train
export HOME_TRAINER=$WORKSPACE/diffusion-pipe
export HOME_AIT=$WORKSPACE/aitools
export CONF_AIT=$HOME_AIT/conf
export PYTHONPATH=$HOME_AIT/src

___train_install_aitools() {
  git clone $REPOS_AIT $HOME_AIT
  pip install -r $HOME_AIT/requirements_remote.txt
}
___train_install_flash_attn() {
  # Install flash-attn with three-tier precedence:
  #   (1) LOCAL STASH    — wheel previously stashed at ${FLASH_ATTN_STASH}/<axes>/
  #   (2) UPSTREAM WHEEL — prebuilt wheel from GitHub Releases, also saved to stash
  #   (3) SOURCE COMPILE — pip wheel into stash dir, then install (~20-40 min once,
  #                        free on subsequent runs of any box with matching axes)
  # Override version via FLASH_ATTN_VER, stash root via FLASH_ATTN_STASH (default
  # ${WORKSPACE}/wheels — Vast.AI's /workspace is persistent across container restarts).
  local ver="${FLASH_ATTN_VER:-2.8.3}"
  local cuda torch_ver py_ver cxx_abi wheel http_code wheel_basename
  local stash_root stash_dir stash_pattern stash_hit
  local t_start t_end elapsed compile_start compile_elapsed

  t_start=$(date +%s)

  echo
  echo "================================================================="
  echo "  flash-attn install  (target version: ${ver})"
  echo "================================================================="

  echo "[1/5] detecting environment ..."
  cuda=$(python3 -c 'import torch; v=torch.version.cuda or ""; print(v.split(".")[0])')
  torch_ver=$(python3 -c 'import torch; v=torch.__version__.split("+")[0].split("."); print(f"{v[0]}.{v[1]}")')
  py_ver=$(python3 -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')
  cxx_abi=$(python3 -c 'import torch; print("TRUE" if torch.compiled_with_cxx11_abi() else "FALSE")')
  echo "      cuda=cu${cuda}  torch=${torch_ver}  python=${py_ver}  cxx11abi=${cxx_abi}"

  # Stash layout: one subdir per (cuda, torch, python, cxx_abi) combo
  stash_root="${FLASH_ATTN_STASH:-${WORKSPACE:-/workspace}/wheels}"
  stash_dir="${stash_root}/flash_attn/cu${cuda}-torch${torch_ver}-${py_ver}-abi${cxx_abi}"
  stash_pattern="${stash_dir}/flash_attn-${ver}*-${py_ver}-${py_ver}-linux_x86_64.whl"

  echo "[2/5] checking local stash ..."
  echo "      $stash_dir"
  stash_hit=$(ls $stash_pattern 2>/dev/null | head -1)
  if [ -n "$stash_hit" ]; then
    echo "      ✓ STASH HIT: $(basename "$stash_hit")"
    echo "[3/5] installing from stash ..."
    if pip install "$stash_hit"; then
      t_end=$(date +%s)
      elapsed=$((t_end - t_start))
      echo "[5/5] ✓ flash-attn ${ver} installed from STASH (${elapsed}s total)"
      echo "================================================================="
      echo
      return 0
    fi
    echo "      ✗ stash install FAILED — falling through to upstream/source"
  else
    echo "      (no stash hit, miss is fine for first run on this combo)"
  fi

  wheel="https://github.com/Dao-AILab/flash-attention/releases/download/v${ver}/flash_attn-${ver}+cu${cuda}torch${torch_ver}cxx11abi${cxx_abi}-${py_ver}-${py_ver}-linux_x86_64.whl"
  wheel_basename=$(basename "$wheel")
  echo "[3/5] probing upstream wheel availability ..."
  echo "      $wheel"
  http_code=$(curl -sIL -o /dev/null -w '%{http_code}' "$wheel" 2>/dev/null || echo "000")
  echo "      HTTP $http_code"

  if [ "$http_code" = "200" ]; then
    echo "[4/5] WHEEL FOUND → downloading + stashing + installing (~10-30s) ..."
    mkdir -p "$stash_dir"
    if curl -L -f -o "${stash_dir}/${wheel_basename}" "$wheel"; then
      echo "      ✓ stashed at ${stash_dir}/${wheel_basename}"
      if pip install "${stash_dir}/${wheel_basename}"; then
        t_end=$(date +%s)
        elapsed=$((t_end - t_start))
        echo "[5/5] ✓ flash-attn ${ver} installed from prebuilt wheel (${elapsed}s)"
        echo "      future runs on this combo will hit the stash and skip download"
      else
        t_end=$(date +%s)
        elapsed=$((t_end - t_start))
        echo "[5/5] ✗ wheel install FAILED (${elapsed}s)"
        return 1
      fi
    else
      echo "      ✗ wheel download FAILED — falling through to source compile"
      http_code="000"  # force the compile branch below
    fi
  fi

  if [ "$http_code" != "200" ]; then
    echo
    echo "      ┌──────────────────────────────────────────────────────────┐"
    echo "      │  NO PREBUILT WHEEL (HTTP $http_code) for this combo:             │"
    echo "      │    flash-attn version : ${ver}"
    echo "      │    cuda               : cu${cuda}"
    echo "      │    torch              : ${torch_ver}"
    echo "      │    python             : ${py_ver}"
    echo "      │    cxx11abi           : ${cxx_abi}"
    echo "      │                                                          │"
    echo "      │  FALLING BACK TO SOURCE COMPILE.                         │"
    echo "      │  Expected wall-clock: ~20-40 min on H100, ~10 min once   │"
    echo "      │  NVCC parallel build kicks in. Do NOT interrupt.         │"
    echo "      │                                                          │"
    echo "      │  The compiled wheel will be saved to the stash dir, so   │"
    echo "      │  subsequent boxes with matching axes install in ~10s.    │"
    echo "      │  Stash: ${stash_dir}"
    echo "      └──────────────────────────────────────────────────────────┘"
    echo
    echo "[4/5] SOURCE COMPILE → starting at $(date '+%Y-%m-%d %H:%M:%S') ..."
    mkdir -p "$stash_dir"
    compile_start=$(date +%s)
    if pip wheel --no-build-isolation -w "$stash_dir" "flash-attn==${ver}"; then
      t_end=$(date +%s)
      compile_elapsed=$((t_end - compile_start))
      stash_hit=$(ls ${stash_dir}/flash_attn-${ver}*-${py_ver}-${py_ver}-linux_x86_64.whl 2>/dev/null | head -1)
      if [ -z "$stash_hit" ]; then
        echo "      ✗ compile reported success but no wheel found in $stash_dir"
        return 1
      fi
      echo "      ✓ stashed at $stash_hit  (compile ${compile_elapsed}s = $((compile_elapsed / 60))m $((compile_elapsed % 60))s)"
      echo "[5/5] installing compiled wheel ..."
      if pip install "$stash_hit"; then
        t_end=$(date +%s)
        elapsed=$((t_end - t_start))
        echo "      ✓ flash-attn ${ver} installed via SOURCE COMPILE"
        echo "      compile time:  ${compile_elapsed}s ($((compile_elapsed / 60))m $((compile_elapsed % 60))s)"
        echo "      total elapsed: ${elapsed}s"
        echo "      stash:         $stash_hit"
        echo "      future runs on this combo will hit the stash and skip compile"
      else
        t_end=$(date +%s)
        elapsed=$((t_end - t_start))
        echo "      ✗ compiled-wheel install FAILED (${elapsed}s)"
        return 1
      fi
    else
      t_end=$(date +%s)
      compile_elapsed=$((t_end - compile_start))
      elapsed=$((t_end - t_start))
      echo "[5/5] ✗ flash-attn ${ver} SOURCE COMPILE FAILED after ${compile_elapsed}s"
      return 1
    fi
  fi
  echo "================================================================="
  echo
}
___train_install_trainer() {
  rm -rf $HOME_TRAINER
  git clone ${REPOS_TRAINER_BRANCH:+--branch $REPOS_TRAINER_BRANCH} $REPOS_TRAINER $HOME_TRAINER
  cd $HOME_TRAINER
  git submodule update --init --recursive

  ___train_install_flash_attn
  pip install -r requirements.txt

  #pip uninstall diffusers
  #yes | pip install git+https://github.com/huggingface/diffusers
  pip install -U "diffusers==0.35.*"
}
train_install() {
  ___train_install_aitools
  ___train_install_trainer
}
train_prepare() {
  python3 $HOME_AIT/script/train_prepare.py
  cp $DIR_TRAIN/train.sh $HOME_TRAINER
}
train_run() {
  train_prepare
  cd $HOME_TRAINER
  ./train.sh
}
clean_train() {
  rm -rf $DIR_TRAIN
}

clean_dataset() {
  rm -rf $DIR_TRAIN/dataset
}

clean_output() {
  rm -rf $DIR_TRAIN/output
}


alias t='vi $HOME_AIT/script/train_prepare.py'

ait_pull() {
  echo "update aitools ..."
  git -C $HOME_AIT pull
}

