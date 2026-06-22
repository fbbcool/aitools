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
___train_install_torch_pin() {
  # Vast.AI's pytorch:cuda-*-auto images can ship torch versions newer than the
  # flash-attn wheel matrix covers (e.g. torch 2.11 → no wheel in flash-attn 2.8.3).
  # Pin torch to a version with a known flash-attn wheel BEFORE the flash-attn install.
  # Override via TORCH_PIN_VER. Empty value disables the pin entirely.
  local pin="${TORCH_PIN_VER-2.9.*}"
  local current
  if [ -z "$pin" ]; then
    echo "[torch pin] disabled (TORCH_PIN_VER is empty)"
    return 0
  fi
  current=$(python3 -c 'import torch; print(torch.__version__.split("+")[0])' 2>/dev/null || echo "none")

  echo
  echo "================================================================="
  echo "  torch pin  (target: ${pin})"
  echo "================================================================="
  echo "  current : ${current}"
  echo "  target  : ${pin}"

  # Cheap match check: if current already satisfies the pin's major.minor, no-op.
  local pin_mm="${pin%.*}"  # strip trailing ".*" → "2.9"
  case "$current" in
    "${pin_mm}".*)
      echo "  ✓ already on ${pin_mm} family, skipping install"
      echo "================================================================="
      echo
      return 0
      ;;
  esac

  echo "  installing 'torch==${pin}' (this overwrites the image's torch) ..."
  if pip install "torch==${pin}"; then
    current=$(python3 -c 'import torch; print(torch.__version__.split("+")[0])')
    echo "  ✓ torch pinned to ${current}"
  else
    echo "  ✗ torch pin FAILED — leaving image's torch in place (${current})"
    echo "  flash-attn install may fall through to source compile"
  fi
  echo "================================================================="
  echo
}
___train_install_flash_attn() {
  # Pull the prebuilt flash-attn wheel matching the active torch/cuda/python/cxx-abi
  # combo. Wheels live on GitHub Releases (not PyPI), so a direct URL pull avoids
  # the ~30 min source compile. Falls back to source compile if no matching wheel
  # exists for the detected combo. Override version via FLASH_ATTN_VER env var.
  local ver="${FLASH_ATTN_VER:-2.8.3}"
  local cuda torch_ver py_ver cxx_abi wheel http_code
  local t_start t_end elapsed compile_start compile_elapsed

  t_start=$(date +%s)

  echo
  echo "================================================================="
  echo "  flash-attn install  (target version: ${ver})"
  echo "================================================================="

  echo "[1/4] detecting environment ..."
  cuda=$(python3 -c 'import torch; v=torch.version.cuda or ""; print(v.split(".")[0])')
  torch_ver=$(python3 -c 'import torch; v=torch.__version__.split("+")[0].split("."); print(f"{v[0]}.{v[1]}")')
  py_ver=$(python3 -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')
  cxx_abi=$(python3 -c 'import torch; print("TRUE" if torch.compiled_with_cxx11_abi() else "FALSE")')
  echo "      cuda=cu${cuda}  torch=${torch_ver}  python=${py_ver}  cxx11abi=${cxx_abi}"

  wheel="https://github.com/Dao-AILab/flash-attention/releases/download/v${ver}/flash_attn-${ver}+cu${cuda}torch${torch_ver}cxx11abi${cxx_abi}-${py_ver}-${py_ver}-linux_x86_64.whl"
  echo "[2/4] probing wheel availability ..."
  echo "      $wheel"
  http_code=$(curl -sIL -o /dev/null -w '%{http_code}' "$wheel" 2>/dev/null || echo "000")
  echo "      HTTP $http_code"

  if [ "$http_code" = "200" ]; then
    echo "[3/4] WHEEL FOUND → installing from prebuilt wheel (~10-30s) ..."
    if pip install "$wheel"; then
      t_end=$(date +%s)
      elapsed=$((t_end - t_start))
      echo "[4/4] ✓ flash-attn ${ver} installed from prebuilt wheel (${elapsed}s total)"
    else
      t_end=$(date +%s)
      elapsed=$((t_end - t_start))
      echo "[4/4] ✗ wheel install FAILED (${elapsed}s)"
      return 1
    fi
  else
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
    echo "      │  To get a wheel instead: check the four axes against     │"
    echo "      │  https://github.com/Dao-AILab/flash-attention/releases/  │"
    echo "      │  and pin FLASH_ATTN_VER to one whose wheel matrix covers │"
    echo "      │  this combo.                                             │"
    echo "      └──────────────────────────────────────────────────────────┘"
    echo
    echo "[3/4] SOURCE COMPILE → starting at $(date '+%Y-%m-%d %H:%M:%S') ..."
    compile_start=$(date +%s)
    if pip install --no-build-isolation "flash-attn==${ver}"; then
      t_end=$(date +%s)
      compile_elapsed=$((t_end - compile_start))
      elapsed=$((t_end - t_start))
      echo "[4/4] ✓ flash-attn ${ver} installed via SOURCE COMPILE"
      echo "      compile time:  ${compile_elapsed}s ($((compile_elapsed / 60))m $((compile_elapsed % 60))s)"
      echo "      total elapsed: ${elapsed}s"
    else
      t_end=$(date +%s)
      compile_elapsed=$((t_end - compile_start))
      elapsed=$((t_end - t_start))
      echo "[4/4] ✗ flash-attn ${ver} SOURCE COMPILE FAILED after ${compile_elapsed}s"
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

  ___train_install_torch_pin
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

