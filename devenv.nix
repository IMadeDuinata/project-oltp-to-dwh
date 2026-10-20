{
  pkgs,
  ...
}:
let
  mkMySQL = import ./mysql.nix { inherit pkgs; };
in
{
  languages.python = {
    enable = true;
    venv = {
      enable = true;
      requirements = builtins.readFile ./requirements.txt;
    };
    libraries = with pkgs; [
      zlib
      stdenv.cc.cc.lib
      libffi
      openssl
      bzip2
      xz
    ];
  };

  packages = [
    pkgs.mysql84
  ];

  scripts = {
    etl.exec = "python etl/run_etl.py \"$@\"";
    scheduler.exec = "python scheduler/run_scheduler.py \"$@\"";
    dashboard.exec = "streamlit run dashboard/main.py \"$@\"";
  };

  processes = {
    mysql-oltp-br = mkMySQL "oltp-br" 3306;
    mysql-oltp-id = mkMySQL "oltp-id" 3307;
    mysql-dwh     = mkMySQL "dwh"     3308;
    dashboard.exec = "streamlit run dashboard/main.py --server.port 8501";
  };

  dotenv.enable = true;
}

