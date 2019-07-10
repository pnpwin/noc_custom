# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------
# ManagedObject
# ----------------------------------------------------------------------
# Copyright (C) 2007-2019 The NOC Project
# See LICENSE for details
# ----------------------------------------------------------------------

# Python modules
import logging
from noc.main.models.notificationgroup import NotificationGroup

logger = logging.getLogger(__name__)


def threshold_escalation(notification_group_id, subject, body):
    notification_group = NotificationGroup.get_by_id(notification_group_id)
    if notification_group:
        try:
            notification_group.notify(subject, body)
        except Exception as e:
            logger.info("Sending notification error %s", e)
        logger.info("Sending notification to group %s", notification_group.name)
    else:
        logger.info("Invalid notification group %s", notification_group_id)



