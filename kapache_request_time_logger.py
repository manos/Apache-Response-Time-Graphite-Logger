#!/usr/local/bin/kpython
###
### This script is designed to be executed via apache CustomLog "|/path/to/$this", and:
### munge the Log data from stdin (URI) in the following way (in order):
###   1) convert dots to underscores,
###   2) convert centrally-located / to dots (which creates a tree structure in graphite)
###      i.e. /foo/bar.gif => foo.bar_gif or /foo/bar/baz.gif => foo.bar.baz_gif
### and then take the first chunk or the URL (/foo), seperate from the rest, to log both..
### and finally send the two stats to statsd, using krux-statsd: (https://github.com/krux/python-kruxstatsd)
###
### read stdin (forever) for apache data which we'll assume has a "%U %D" LogFormat, e.g. "/path/foo.gif 22000"

import kruxstatsd 
import sys
from optparse import OptionParser

# function to convert the %U from apache to "top level" (i.e. the first part of the URI, i.e. "foo" in /foo/bar), and
# "full", i.e. foo.bar in /foo/bar. This implementation is probably site-specific. In fact, many people may only be
# interested in "top level," which is fine.
def convert_input_to_keys(data):
    path, request_time = data
    path = path.rstrip('/').lstrip('/').replace('.', '_')
    if '/' in path:
        parts = path.split('/')
        endpoint_top_level = parts[0]
        endpoint_full = '/'.join(parts).replace('/', '.')
    else:
        endpoint_top_level = path
        endpoint_full = None
    request_time = int(request_time) / 1000

    return request_time, endpoint_top_level, endpoint_full

# parse some options!
parser = OptionParser()
parser.add_option("--cluster", help="The cluster_name stats will be grouped in", dest="cluster_name", default="ungrouped")
(options, args) = parser.parse_args()

# this determins the first part of the graphite layout. e.g. timers.httpd.${cluster_name}
stat_name = 'httpd.' + options.cluster_name

# before we loop forever(!), determine our environment (dev, prod, etc) and set krux_env:
puppet_conf = open("/etc/puppet/puppet.conf", "r").readlines()
for lines in puppet_conf:
    if "environment" in lines:
        if "=" not in lines:
            continue
        env = lines.split()[2].lstrip('"').rstrip('"')

# our statsd uses short form names, so translate from puppet's config to krux-statsd:
if 'development' in env:
    sys.stdout.write("kapache_request_time_logger successfully discovered environment=dev\n")
    krux_env = "dev"
elif 'production' in env:
    sys.stdout.write("kapache_request_time_logger successfully discovered environment=prod\n")
    krux_env = "prod"
else:
    sys.stderr.write("kapache_request_time_logger is unable to determine environment in known set! shoving in environment=prototype for now..\n")
    krux_env = "prototype"

# now, read what apache sent from stdin, forever:
for apache_says in sys.stdin:
    request_time, endpoint_top_level, endpoint_full = convert_input_to_keys(apache_says.split())

    # we used to log endpoint_full and all sorts of craziness, until it broke graphite. trimmed down version:
    #  logging only /foo (NOTE: we're not even using endpoint_full any more).
    k = kruxstatsd.StatsClient(stat_name, env=krux_env)

    k.timing(endpoint_top_level + '.request_time', request_time)
    k.incr(endpoint_top_level) # log a counter for req/s, too

    k.incr("_total_cluster_requests") # also, log a hit for cluster-level req/s!


