import os
import sys
import logging
from datetime import datetime

# sys.path.append("/home/ikwen/Clients/Zovizo")
sys.path.append("/home/komsihon/Dropbox/PycharmProjects/Zovizo")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")

from zovizo.utils import register_members_for_next_draw, pick_up_winner

logger = logging.getLogger('ikwen.crons')


if __name__ == "__main__":
    try:
        t0 = datetime.now()
        try:
            DEBUG = sys.argv[1] == 'debug'
        except IndexError:
            DEBUG = False
        if DEBUG:
            print "Draw started in debug mode"
        register_members_for_next_draw(DEBUG)
        pick_up_winner(DEBUG)
        diff = datetime.now() - t0
        logger.debug("Draw run in %s" % diff)
    except:
        logger.error("Fatal error occured, draw not run", exc_info=True)
