import logging


def init(args):
    level = [logging.INFO, logging.DEBUG][args.debug]
    logging.basicConfig(format="[%(process)d|%(asctime)s] %(message)s", level=level)


def debug(message):
    logging.debug(message)


def info(message):
    logging.info(message)


def error(message):
    logging.error(message)
