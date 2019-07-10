# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------
#  Interface Alarm handlers
# ----------------------------------------------------------------------
#  Copyright (C) 2007-2019 The NOC Project
#  See LICENSE for details
# ----------------------------------------------------------------------

# Python modules
import logging
import datetime
import time
# NOC modules
from noc.inv.models.interface import Interface
from noc.pm.models.metrictype import MetricType
from noc.fm.models.alarmescalation import AlarmEscalation
from noc.sa.models.selectorcache import SelectorCache
from noc.sa.models.managedobject import ManagedObject
from noc.fm.models.alarmlog import AlarmLog

from noc.core.defer import call_later

logger = logging.getLogger(__name__)


def humanize_speed(speed, type_speed):

    d_speed = {
        "bit/s": [(1000000000, "Gbit/s"), (1000000, "Mbit/s"), (1000, "kbit/s")],
        "kbit/s": [(1000000, "Gbit/s"), (1000, "Mbit/s")]
    }

    if speed < 1000 and speed > 0:
        return "%s " % speed
    for t, n in d_speed.get(type_speed):
        if speed >= t:
            if speed // t * t == speed:
                return "%d %s" % (speed // t, n)
            else:
                return "%.2f %s" % (float(speed) / t, n)


def handler(mo, alarm):
    # Date Time Block
    from_date = datetime.datetime.now() - datetime.timedelta(hours=6)
    date_limit = datetime.datetime.now() - datetime.timedelta(days=6)
    # interval = (to_date - from_date).days
    ts_from_date = time.mktime(from_date.timetuple())
    ts_date_limit = time.mktime(date_limit.timetuple())
    if ts_from_date < ts_date_limit:
        ts_from_date = ts_date_limit
    metric = MetricType.objects.get(name=alarm['vars']['metric'])
    periodic_interval = mo.object.object_profile.periodic_discovery_interval
    if alarm['vars']["window_type"] == "m":
        threshold_interval = periodic_interval * alarm['vars']["window"]

    iface = Interface.objects.get(name=alarm["vars"]["path"].split("|")[-1::][0].strip(), managed_object=mo.object)
    try:
        if iface:
            if iface.in_speed and iface.out_speed:
                if "In" in alarm['vars']['metric']:
                    iface_speed = iface.in_speed
                else:
                    iface_speed = iface.out_speed
                alarm['vars']['percent'] = round((100.0 / int(iface_speed)) * ((alarm['vars']['value']) / 1000))

            alarm['vars']["interface"] = alarm["vars"]["path"].split("|")[-1::][0].strip()
            alarm['vars']["description"] = str(iface.description)
            alarm['vars']['convert_value'] = humanize_speed(alarm['vars']['value'], metric.measure)
            alarm['vars']['threshold_interval'] = int(threshold_interval) / 60
            alarm['vars']['ts_from_date'] = str(int(ts_from_date * 1000))
            alarm['vars']['mo'] = mo.object.name.replace("#", "%2F")
            if mo.object.can_notify():
                ctx = {
                    "alarm": alarm,
                    "managed_object": {"name": mo.object.name,
                                       "bi_id": mo.object.bi_id}
                }
                esc = alarm_escalation(alarm, mo, ctx)
                if esc:
                    alarm['clear_notification_group'] = esc["notification_group"]
                    alarm['clear_template'] = esc["clear_template"]
                    alarm['log'] = [AlarmLog(
                                        timestamp=datetime.datetime.now(),
                                        from_status="A",
                                        to_status="A",
                                        message=esc["message"])]
            return alarm
    except Exception as e:
        logger.info("Error: \n %s" % (alarm["vars"]["path"].split("|")[-1::][0].strip(), e))
        return alarm


def alarm_escalation(alarm, mo, ctx):
    now = datetime.datetime.now()
    for esc in AlarmEscalation.get_class_escalations(alarm['alarm_class']):
        for e_item in esc.escalations:
            # Check administrative domain
            if (e_item.administrative_domain and
                    e_item.administrative_domain.id not in mo.object.administrative_domain.get_path()):
                continue
            # Check severity
            if e_item.min_severity and alarm['severity'] < e_item.min_severity:
                continue
            # Check selector
            if e_item.selector and not SelectorCache.is_in_selector(mo.object, e_item.selector):
                continue
            logger.info(
                "%s Watch for %s after %s seconds",
                alarm['alarm_class'], esc.name, e_item.delay
            )
            et = now + datetime.timedelta(seconds=e_item.delay)
            if et > now:
                delay = (et - now).total_seconds()
            else:
                delay = None
            if e_item.notification_group:
                subject = e_item.template.render_subject(**ctx)
                body = e_item.template.render_body(**ctx)
                logger.debug("Notification message:\nSubject: %s\n%s", subject, body)
                call_later(
                    "noc.custom.handlers.thresholds.thresholdsnotification.threshold_escalation",
                    delay=delay,
                    scheduler="scheduler",
                    notification_group_id=e_item.notification_group.id,
                    subject=subject,
                    body=body
                )
                return {"notification_group": e_item.notification_group,
                        "clear_template": e_item.clear_template,
                        "message": "Sending message to : %s" % e_item.notification_group.name}
            #
            if e_item.stop_processing:
                logger.debug("Stopping processing")
                break
