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

  processes = {
    mysql-oltp-br = mkMySQL "oltp-br" 3306;
    mysql-oltp-id = mkMySQL "oltp-id" 3307;
    mysql-dwh     = mkMySQL "dwh"     3308;
  };

  dotenv.enable = true;
}

