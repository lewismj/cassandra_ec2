# Cassandra EC2
This repository provides some simple Python scripts for creating an Apache Cassandra cluster using EC2 instances. Useful if you want to spin up a development cluster using script, without relying on DCOS or similar. Intended for spinning up development clusters only. Even for development purposes, do specify the authorised addresses flag. Or, manually reconfigure the security group inbound rules once cluster is up and running.

I’ve taken some things from the [SparkEC2][1] project.

*Under development, currently just the ‘create’ action is supported.*

## Todo

- 1. Implement the destroy command.
- 2. Make the options a configuration file.
- 3. Allow more configuration, easily setup multi-region clusters.


## Name
**`cassandra_ec2.py [options] `**

## Description
Briefly, this script will:

- create a security group.
- launch the desired number of instances, with storage.
- wait for the cluster to start (i.e. can ‘ssh’ to the instances).
- download the desired version of Apache Cassandra.
- copy Cassandra to each instance.
- perform a number of ‘sed’ edits on each ‘cassandra.yaml’ file.

## Options

- **-u --user** The SSH user you want to connect to your instances as (default: ec2-user).
- **-r -—region** EC2 region name (default: eu-central-1).
- **-z -—zone** The availability zone to use (default: eu-central-1b).
- **-i -—identity-file** SSH private key 
- **-k -—key-pair** The key-pair name to use on instances.
- **-t -—instance-type** Instance type of instance to launch (default: m1.large).
- **-m -—ami** Amazon machine image ID to use.
- **-s -—ebs-vol-size** Size (in GB) of each EBS volume (default: 8GB).
- **-e -—ebs-vol-type** EBS volume type, e.g. ‘gp2’ (default: standard).
- **-d -—authorized-address** Address to authorise on created security groups (default: 0.0.0.0/0).
- **-v -—vpc-id** VPC id of VPC to launch instance in.
- **-c -—node-count** Number of nodes to create for the cluster.
- **-a -—action** The action to perform (‘create’, ‘destroy’).
- **-n -—name** The name of the cluster.
- **-o -—version** The version of Cassandra to deploy.

## Configuration setup
At present a minimal set of changes are made to the `cassandra.yaml` file. These are implemented in the function shown below:
```python
def unpack_and_edit_config_files(file_name, dns_names, args):
    short_file_name = file_name.split("/")[-1]
    unpacked_dir = "apache-cassandra-{version}".format(version=args.version)

    num_seeds = min(len(dns_names), 2)
    seed_list = []
    for i in range(0, num_seeds):
        seed_list.append(dns_names[i][1])
    seeds = ",".join(seed_list)

    for dns in dns_names:
        public_name = dns[0]
        private_ip = dns[1]

        # minimal set of commands, need to change snitch etc...
        commands = [
            # Unpack tar file.
            "tar -zxf {file}".format(file=short_file_name),

            # rename the cluster.
            "sed -i -e 's/Test Cluster/{name}/g' {dir}/conf/cassandra.yaml".format(name=args.name, dir=unpacked_dir),

            # change the listen address.
            "sed -i -e 's/listen_address: localhost/listen_address: {ip}/g' {dir}/conf/cassandra.yaml"
            .format(ip=private_ip, dir=unpacked_dir),

            # change the rpc addresses.
            "sed -i -e 's/rpc_address: localhost/rpc_address: {ip}/g' {dir}/conf/cassandra.yaml"
            .format(ip=private_ip, dir=unpacked_dir),

            # add in a broadcast address.
            "echo \"broadcast_address: {ip} \" | tee -a {dir}/conf/cassandra.yaml"
            .format(ip=private_ip, dir=unpacked_dir),

            # change data file location.
            "echo \"data_file_directories:\n- /data/cassandra/data\"  | tee -a {dir}/conf/cassandra.yaml"
            .format(dir=unpacked_dir),

            # put value for the seeds.
            "sed -i -e 's/seeds: \"127.0.0.1\"/seeds: \"{seeds}\"/g' {dir}/conf/cassandra.yaml"
            .format(seeds=seeds, dir=unpacked_dir),

            # change the snitch.
            "sed -i -e 's/endpoint_snitch: SimpleSnitch/endpoint_snitch: Ec2Snitch/g' {dir}/conf/cassandra.yaml"
            .format(dir=unpacked_dir),

            # install java 8.
            "sudo yum -y install java-1.8.0; sudo yum -y remove java-1.7.0-openjdk",

            # create directories.
            "sudo mkdir -p /data",

            # mount the storage used for storing data.
            # ** n.b. Assumes just one disk atm. **
            'sudo mkfs -t ext4 /dev/xvdt; sudo mount /dev/xvdt /data',

            # create the mount point.
            'sudo mkdir -p /data/cassandra/data",'

            # make sure Cassandra can write to the data location.
            'sudo chown -fR ec2-user /data/cassandra/',

            # run Cassandra.
            '{dir}/bin/cassandra'.format(dir=unpacked_dir)
        ]
        command = ";".join(commands)
        ssh(public_name, args, command)
```

## Example Output


[1]:	https://github.com/amplab/spark-ec2
