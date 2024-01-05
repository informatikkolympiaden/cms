{config, options, lib, pkgs, ... }:

let
    cfg = config.services.cms;

    cmsPkg = pkgs.callPackage (import ./default.nix) {};

    configFile = pkgs.writeText "cms.conf" (builtins.toJSON cfg.settings);

    systemdServices = map ({service, options, shard}: {
        "cms-service-${service}-${toString shard}" = {
            wantedBy = ["cms-services.target"];
            after = ["cms-postgres-ready.service"];

            environment.CMS_CONFIG = cfg.configFile;
            path = [ 
                cfg.package 
                config.programs.isolate.env
            ];
            script = ''
                cms${service} ${lib.escapeShellArgs options} ${toString shard}
            '';

            serviceConfig = if service == "Worker" then {
                User="root";
            } else {
                User="cmsuser";
                StateDirectory="cms";
                WorkingDirectory="/var/lib/cms";
            };
        };
    }) cfg.services;
in
{
    imports = [
        (import ../isolate/nixos-module.nix)
    ];

    options.services.cms = {
        enable = lib.mkEnableOption "Contest Management System";

        package = lib.mkOption {
            type = lib.types.path;
            default = cmsPkg;
        };

        configFile = lib.mkOption {
            type = lib.types.path;
            default = configFile;
        };

        user = lib.mkOption {
            type = lib.types.str;
            default = "cmsuser";
        };

        settings = lib.mkOption {
            type = (pkgs.formats.json {}).type;
            default = {};
        };

        db = {
            user = lib.mkOption {
                type = lib.types.str;
                default = "cmsuser";
            };

            database = lib.mkOption {
                type = lib.types.str;
                default = "cmsdb";
            };

            password = lib.mkOption {
                type = lib.types.str;
                default = "pass";
            };

            address = lib.mkOption {
                type = lib.types.str;
                default = "localhost";
            };
        };

        services = lib.mkOption {
            default = [];
            type = lib.types.listOf (lib.types.submodule ({...}: {
                options.service = lib.mkOption {
                    type = lib.types.str;
                };
                options.shard = lib.mkOption {
                    type = lib.types.nullOr lib.types.int;
                    default = null;
                };
                options.options = lib.mkOption {
                    type = lib.types.listOf lib.types.str;
                    default = [];
                };
            }));
        };
    };

    config = lib.mkIf cfg.enable {
        programs.isolate.enable = true;

        services.cms.settings.cmsuser = cfg.user;
        services.cms.settings.shared_mime_info_prefix = "${pkgs.shared-mime-info}/usr";
        services.cms.settings.database = "postgresql+psycopg2://${cfg.db.user}:${cfg.db.password}@${cfg.db.address}:5432/${cfg.db.database}";

        users.users.${cfg.user} = {
            isSystemUser = lib.mkDefault true;
            group = cfg.user;
        };
        users.groups.${cfg.user} = {};

        environment.systemPackages = [
            cfg.package
        ];

        environment.variables.CMS_CONFIG = cfg.configFile;

        systemd.services = lib.mkMerge (systemdServices ++ [{
            cms-postgres-ready = {
                wantedBy = ["cms-services.target"];

                script = ''
                    until ${pkgs.postgresql}/bin/pg_isready -h ${cfg.db.address}; do
                        sleep 1
                    done
                    sleep 5
                '';

                serviceConfig = {
                    User = "cmsuser";
                    Type = "oneshot";
                    RemainAfterExit = "yes";
                };
            };
        }]);

        systemd.targets.cms-services = lib.mkIf (cfg.services != []) {
            wantedBy = ["multi-user.target"];
        };
    };
}
