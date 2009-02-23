import os

from nose import plugins

from paste.deploy import appconfig

conf = None

class Plugin(plugins.Plugin):
    name = "restish"
    enable = False
    enableOpt = "NOSE_PASTE_WITH_CONFIG"
    config_file = None

    def options(self, parser, env=os.environ):
        parser.add_option("--with-config",
                          dest="config_file",
                          type="string",
                          help="Load environnement variables from config file. [%s]" % self.enableOpt)

        plugins.Plugin.options(self, parser, env=os.environ)

    def configure(self, options, conf):
        plugins.Plugin.configure(self, options, conf)

        if options.config_file:
            self.enabled = True
            self.config_file = options.config_file

    def begin(self):
        global conf

        conf = appconfig("config:%s" % os.path.join(os.getcwd(), self.config_file))
        conf["__file__"] = self.config_file

