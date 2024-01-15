export ENV_REPOS='https://github.com/fbbcool/aitools.git'
export ENV_PWD=`pwd`
export ENV_HOME=$ENV_PWD/___aitools

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

