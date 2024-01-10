export ENV_REPOS='https://github.com/fbbcool/aitools.git'
export ENV_PWD=`pwd`
export ENV_HOME=$ENV_PWD/aitools

install_train() {
    rm -rf $ENV_HOME
    git clone $ENV_REPOS $ENV_HOME
    source $ENV_HOME/env/env_train.sh
    env_inst
}
