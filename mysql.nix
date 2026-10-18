{ pkgs }:
name: port: {
  exec = ''
    DATA_DIR="$DEVENV_STATE/mysql-${name}"
    mkdir -p "$DATA_DIR"

    if [ ! -d "$DATA_DIR/mysql" ]; then
      ${pkgs.mysql84}/bin/mysqld --initialize-insecure \
        --datadir="$DATA_DIR" --user=$(whoami)
    fi

    exec ${pkgs.mysql84}/bin/mysqld \
      --datadir="$DATA_DIR" \
      --port=${toString port} \
      --socket="$DEVENV_STATE/mysql-${name}.sock" \
      --bind-address=127.0.0.1
  '';
}
