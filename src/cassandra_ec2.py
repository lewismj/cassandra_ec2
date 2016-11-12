#!/usr/bin/env python
#
# Copyright (c) 2016, Michael Lewis
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>
#

from __future__ import print_function

import argparse
import itertools
import string
from datetime import datetime
import subprocess
import time
import pipes
import os
import os.path
import sys
import textwrap
from argparse import ArgumentError
from sys import stderr
from boto.ec2.blockdevicemapping import BlockDeviceMapping, BlockDeviceType, EBSBlockDeviceType
from clint.textui import progress
import requests



__author__ = 'lewismj@waioeka.com'


def parse_args():

    try:
        parser = argparse.ArgumentParser(description="[cassandra_cluster.py] Create EC2 cluster for C*.")
        parser.add_argument('-u', '--user', default="ec2-user",
                            help="The SSH user you want to connect as (default: ec2-user).")
        parser.add_argument('-r', '--region', default="eu-central-1", help="EC2 region name (default: eu-central-1).")
        parser.add_argument('-z', '--zone', default="eu-central-1b", help="Availability zone to use.")
        parser.add_argument('-i', '--identity-file', help="SSH private key file to use for logging into instances.")
        parser.add_argument('-k', '--key-pair', help='Key pair name to use on instances.')
        parser.add_argument('-t', "--instance-type", default="m1.large",
                            help="Instance type of instance to launch (default: m1.large).")
        parser.add_argument('-m', "--ami", required=True, help="Amazon Machine Image ID to use.")
        parser.add_argument('-s', "--ebs-vol-size", metavar="SIZE", type=int, default=8,
                            help="Size (in GB) of each EBS volume (default: 50 GB).")
        parser.add_argument('-e', "--ebs-vol-type", default="standard", help="EBS volume type (e.g. 'gp2').")
        parser.add_argument('-d', "--authorized-address",  default="0.0.0.0/0",
                            help="Address to authorize on created security groups (default: 0.0.0.0/0).")
        parser.add_argument('-v', "--vpc-id", required=True, help="VPC id to launch instances in.")
        parser.add_argument('-c', "--node_count", type=int, default=3, help="Number of nodes in the cluster.")
        parser.add_argument('-a', "--action", required=True, help="Action to perform ('create' or 'destroy'.")
        parser.add_argument('-n', "--name", required=True, help="The name of the cluster.")
        parser.add_argument('-o', "--version", default="3.9", help="The version of Cassandra to deploy.")
        return parser.parse_args()

    except (ArgumentError, Exception) as e:
        print ("[cassandra_cluster.py] __main__ caught exception: ", e, file=stderr)
        sys.exit(1)


# Get number of local disks available for a given EC2 instance type.
def get_num_disks(instance_type):
    # Source: http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/InstanceStorage.html
    # Last Updated: 2015-06-19
    # For easy maintainability, please keep this manually-inputted dictionary sorted by key.
    disks_by_instance = {
        "c1.medium":   1,
        "c1.xlarge":   4,
        "c3.large":    2,
        "c3.xlarge":   2,
        "c3.2xlarge":  2,
        "c3.4xlarge":  2,
        "c3.8xlarge":  2,
        "c4.large":    0,
        "c4.xlarge":   0,
        "c4.2xlarge":  0,
        "c4.4xlarge":  0,
        "c4.8xlarge":  0,
        "cc1.4xlarge": 2,
        "cc2.8xlarge": 4,
        "cg1.4xlarge": 2,
        "cr1.8xlarge": 2,
        "d2.xlarge":   3,
        "d2.2xlarge":  6,
        "d2.4xlarge":  12,
        "d2.8xlarge":  24,
        "g2.2xlarge":  1,
        "g2.8xlarge":  2,
        "hi1.4xlarge": 2,
        "hs1.8xlarge": 24,
        "i2.xlarge":   1,
        "i2.2xlarge":  2,
        "i2.4xlarge":  4,
        "i2.8xlarge":  8,
        "m1.small":    1,
        "m1.medium":   1,
        "m1.large":    2,
        "m1.xlarge":   4,
        "m2.xlarge":   1,
        "m2.2xlarge":  1,
        "m2.4xlarge":  2,
        "m3.medium":   1,
        "m3.large":    1,
        "m3.xlarge":   2,
        "m3.2xlarge":  2,
        "m4.large":    0,
        "m4.xlarge":   0,
        "m4.2xlarge":  0,
        "m4.4xlarge":  0,
        "m4.10xlarge": 0,
        "r3.large":    1,
        "r3.xlarge":   1,
        "r3.2xlarge":  1,
        "r3.4xlarge":  1,
        "r3.8xlarge":  2,
        "t1.micro":    0,
        "t2.micro":    0,
        "t2.small":    0,
        "t2.medium":   0,
        "t2.large":    0,
    }
    if instance_type in disks_by_instance:
        return disks_by_instance[instance_type]
    else:
        print("WARNING: Don't know number of disks on instance type %s; assuming 1"
              % instance_type, file=stderr)
        return 1


def get_or_make_group(conn, name, vpc_id):
    groups = conn.get_all_security_groups()
    group = [g for g in groups if g.name == name]
    if len(group) > 0:
        return group[0]
    else:
        print("Creating security group " + name)
        return conn.create_security_group(name, "Cluster group", vpc_id)


def cluster_nodes(conn, name):
    print("Checking to see if cluster is already running...")
    reservations = conn.get_all_reservations(filters={"instance.group-name": name})
    instances = itertools.chain.from_iterable(r.instances for r in reservations)
    live_instances = [i for i in instances if i.state not in ["shutting-down", "terminated"]]

    if any(live_instances):
        print("... found {n} running instances.".format(n=len(live_instances)))
    return live_instances


def stringify_command(parts):
    if isinstance(parts, str):
        return parts
    else:
        return ' '.join(map(pipes.quote, parts))


def ssh_args(args):
    parts = ['-o', 'StrictHostKeyChecking=no']
    parts += ['-o', 'UserKnownHostsFile=/dev/null']
    if args.identity_file is not None:
        parts += ['-i', args.identity_file]
    return parts


def ssh_command(args):
    return ['ssh'] + ssh_args(args)


def is_ssh_available(host, args):
    s = subprocess.Popen(
        ssh_command(args) + ['-t', '-t', '-o', 'ConnectTimeout=5', '%s@%s' % (args.user, host),
                             stringify_command('true')],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT  # we pipe stderr through stdout to preserve output order
    )
    cmd_output = s.communicate()[0]  # [1] is stderr, which we redirected to stdout

    if s.returncode != 0:
        # extra leading newline is for spacing in wait_for_cluster_state()
        print(textwrap.dedent("""\n
            Warning: SSH connection error. (This could be temporary.)
            Host: {h}
            SSH return code: {r}
            SSH output: {o}
        """).format(
            h=host,
            r=s.returncode,
            o=cmd_output.strip()
        ))

    return s.returncode == 0


def is_cluster_ssh_available(instances, args):
    dns_names = get_dns_names(instances)
    for dns in dns_names:
        public_dns = dns[0]
        if not is_ssh_available(host=public_dns, args=args):
            return False
    return True


def wait_for_ssh_state(conn, args, instances):
    print("Waiting for cluster nodes to be 'ssh-ready'")

    start_time = datetime.now()
    num_attempts = 0
    while True:
        time.sleep(5 * num_attempts)

        instance_ids = []
        for i in instances:
            i.update()
            instance_ids.append(i.id)

        statuses = conn.get_all_instance_status(instance_ids=instance_ids)

        if all(i.state == 'running' for i in instances) and \
           all(s.system_status.status == 'ok' for s in statuses) and \
           all(s.instance_status.status == 'ok' for s in statuses) and \
                is_cluster_ssh_available(instances, args):
            break

        num_attempts += 1

    end_time = datetime.now()
    sys.stdout.write(".")
    sys.stdout.flush()

    sys.stdout.write("\n")
    print("Cluster is now 'ssh-ready'. Waited {t} seconds".format(t=(end_time - start_time).seconds))


def create_cluster(conn, args):
    if args.identity_file is None:
        print("ERROR: Must provide an identity file (-i) for ssh connections.", file=stderr)
        sys.exit(1)

    if args.key_pair is None:
        print("ERROR: Must provide a key pair name (-k) to use on instances.", file=stderr)
        sys.exit(1)

    # make or get the security group.
    security_group = get_or_make_group(conn, args.name, args.vpc_id)

    # set the inbound permission rules
    if len(security_group.rules) == 0:
        if args.vpc_id is None:
            security_group.authorize(src_group=security_group)
        else:
            security_group.authorize('tcp', 22, 22, args.authorized_address)
            security_group.authorize('tcp', 8888, 8888, args.authorized_address)
            security_group.authorize('tcp', 7000, 7000, args.authorized_address)
            security_group.authorize('tcp', 7001, 7001, args.authorized_address)
            security_group.authorize('tcp', 7199, 7199, args.authorized_address)
            security_group.authorize('tcp', 9042, 9042, args.authorized_address)
            security_group.authorize('tcp', 9160, 9160, args.authorized_address)
    else:
        print("Security group already exists, skipping creation.")

    instances = cluster_nodes(conn, args.name)
    if any(instances):
        additional_tags = {}
        for i in instances:
            i.add_tags(dict(additional_tags, Name="{cn}-node-{iid}".format(cn=args.name, iid=i.id)))
        return instances
    else:
        print("Launching {m} instances for cluster...".format(m=args.node_count))

        try:
            image = conn.get_all_images(image_ids=args.ami)[0]

            block_map = BlockDeviceMapping()
            if args.ebs_vol_size > 0:
                if args.instance_type.startswith('m3.'):
                    for i in range(get_num_disks(args.instance_type)):
                        device = BlockDeviceType()
                        device.ephemeral_name = "ephemeral%d" %i
                        name = "/dev/sd" + string.ascii_letters[i+1]
                        block_map[name] = device

                else:
                    device = EBSBlockDeviceType()
                    device.size = args.ebs_vol_size
                    device.volume_type = args.ebs_vol_type
                    device.delete_on_termination = True
                    key = "/dev/sd" + chr(ord('s')+1)
                    block_map[key] = device

            nodes = image.run(
                key_name=args.key_pair,
                security_group_ids=[security_group.id],
                instance_type="",
                placement=args.zone,
                min_count=1,
                max_count=1,
                block_device_map=block_map,
                subnet_id=None,
                placement_group=None,
                user_data=None,
                instance_initiated_shutdown_behavior="stop",
                instance_profile_name=None)

            print("Waiting for AWS to propagate instance metadata...")
            time.sleep(15)

            additional_tags = {}
            for node in nodes.instances:
                node.add_tags(dict(additional_tags, Name="{cn}-node-{iid}".format(cn=args.name, iid=node.id)))

            return nodes.instances

        except Exception as e:
            print("Caught exception: ", e)
            print("ERROR: Could not find AMI " + args.ami, file=stderr)
            sys.exit(1)


def get_dns_names(instances, private_ips=False):
    dns_names = []
    for instance in instances:
        public_dns_name = instance.public_dns_name if not private_ips else instance.private_ip_address
        public_ip_addr = instance.ip_address
        if not public_dns_name:
            raise Exception("Failed to determine hostname of {0}".format(instance))
        else:
            dns_names.append((public_dns_name, public_ip_addr))
    return dns_names


def download_and_sync_to_nodes(file_name, dns_names, args):
    short_file_name = file_name.split("/")[-1]
    download_file(file_name)

    for dns in dns_names:
        public_name = dns[0]
        command = [
            "rsync",
            "-rv",
            "-e", stringify_command(ssh_command(args)),
            "/tmp/{0}".format(short_file_name),
            "%s@%s:~/." % (args.user, public_name)
        ]
        ret_code = subprocess.check_call(command)
        if ret_code != 0:
            raise Exception("RSync failure to node {0}".format(public_name))


def unpack_and_edit_config_files(file_name, dns_names, args):
    short_file_name = file_name.split("/")[-1]
    unpacked_dir = "apache-cassandra-{version}".format(version=args.version)

    num_seeds = min(len(dns_names), 3)
    seed_list = []
    for i in range(0, num_seeds):
        seed_list.append(dns_names[i][1])
    seeds = ",".join(seed_list)

    for dns in dns_names:
        public_name = dns[0]
        public_ip = dns[1]

        # minimal set of commands, need to change snitch etc...
        commands = [
            "tar -zxf {file}".format(file=short_file_name),
            "sed -i -e 's/Test Cluster/{name}/g' {dir}/conf/cassandra.yaml".format(name=args.name, dir=unpacked_dir),
            "sed -i -e 's/localhost/{ip}/g' {dir}/conf/cassandra.yaml".format(ip=public_ip, dir=unpacked_dir),
            "sed -i -e 's/seeds: \"127.0.0.1\"/seeds: \"{seeds}\"/g' {dir}/conf/cassandra.yaml"
            .format(seeds=seeds, dir=unpacked_dir)
        ]
        command = ";".join(commands)
        ssh(public_name, args, command)


def download_file(url):
    file_name = url.split('/')[-1]
    r = requests.get(url, stream=True)
    path = "/tmp/{0}".format(file_name)
    with open(path, 'wb') as f:
        sz = int(r.headers.get('content-length'))
        for chunk in progress.bar(r.iter_content(chunk_size=1024), expected_size=(sz/1024) + 1):
            if chunk:
                f.write(chunk)
                f.flush()


def ssh(host, opts, command):
    tries = 0
    while True:
        try:
            return subprocess.check_call(
                ssh_command(opts) + ['-t', '-t', '%s@%s' % (opts.user, host),
                                     stringify_command(command)])
        except subprocess.CalledProcessError as e:
            if tries > 5:
                # If this was an ssh failure, provide the user with hints.
                if e.returncode == 255:
                    raise Exception(
                        "Failed to SSH to remote host {0}.\n"
                        "Please check that you have provided the correct --identity-file and "
                        "--key-pair parameters and try again.".format(host))
                else:
                    raise e
            print("Error executing remote command, retrying after 30 seconds: {0}".format(e),
                  file=stderr)
            time.sleep(30)
            tries += 1


def main():
    args = parse_args()

    home_dir = os.getenv('HOME')
    if home_dir is None or not os.path.isfile(home_dir + '/.boto'):
        if not os.path.isfile('/etc/boto.cfg'):
            if not os.path.isfile(home_dir + '/.aws/credentials'):
                if os.getenv('AWS_ACCESS_KEY_ID') is None:
                    print("ERROR: The environment variable AWS_ACCESS_KEY_ID must be set", file=stderr)
                    sys.exit(1)
                if os.getenv('AWS_SECRET_ACCESS_KEY') is None:
                    print("ERROR: The environment variable AWS_SECRET_ACCESS_KEY must be set", file=stderr)
                    sys.exit(1)

    from boto import ec2
    if args.action == "create":
        try:

            print("Creating cluster ... ", args.name, "in region", args.region)
            conn = ec2.connect_to_region(args.region)
            instances = create_cluster(conn, args)
            wait_for_ssh_state(conn, args, instances)

            print("Downloading Cassandra version {version}".format(version=args.version))
            file_name = "http://apache.mirror.anlx.net/cassandra/{version}/apache-cassandra-{version}-bin.tar.gz" \
                .format(version=args.version)
            dns_names = get_dns_names(instances)
            download_and_sync_to_nodes(file_name, dns_names, args)
            print("Unpacking and editing configuration files.")
            unpack_and_edit_config_files(file_name, dns_names, args)

            print("Cluster setup complete.")
        except Exception as e:
            print(e, file=stderr)
            sys.exit(1)

if __name__ == "__main__":
    """Usage:
        cassandra_ec2.py [options] action cluster_name
    """
    main()
