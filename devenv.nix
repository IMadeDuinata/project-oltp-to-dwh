{
  pkgs,
  ...
}:
{
  languages.python = {
    enable = true;
    venv = {
      enable = true;
      requirements = ./requirements.txt;
    };
  };

  packages = with pkgs; [
    python3Packages.numpy
  ];

  services = {
    mysql = {
      enable = true;
      initialDatabases = [
        { name = "oltp_olist"; }
        { name = "dwh_olist"; }
      ];
    };
  };

  dotenv.enable = true;
}

