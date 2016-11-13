# Cassandra EC2
This repository provides a Python script for creating and managing an Apache Cassandra cluster using EC2 instances. Useful if you want to spin up a development cluster directly on EC2 instances, without relying on DCOS or similar. The script is intended for development clusters only.  Do specify the authorised addresses flag. Or, manually reconfigure the security group once your cluster is up and running. The script will take AMI and EBS volume type & size as parameters. 
The script is loosely based on the scripts for staring Spark found in the[SparkEC2][1] project.

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
- start the Cassandra process.

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

        commands = [
            "tar -zxf {file}".format(file=short_file_name),
            "sed -i -e 's/Test Cluster/{name}/g' {dir}/conf/cassandra.yaml".format(name=args.name, dir=unpacked_dir),
            "sed -i -e 's/listen_address: localhost/listen_address: {ip}/g' {dir}/conf/cassandra.yaml"
            .format(ip=private_ip, dir=unpacked_dir),
            "sed -i -e 's/rpc_address: localhost/rpc_address: {ip}/g' {dir}/conf/cassandra.yaml"
            .format(ip=private_ip, dir=unpacked_dir),
            "echo \"broadcast_address: {ip} \" | tee -a {dir}/conf/cassandra.yaml"
            .format(ip=private_ip, dir=unpacked_dir),
            "echo \"data_file_directories:\n- /data/cassandra/data\"  | tee -a {dir}/conf/cassandra.yaml"
            .format(dir=unpacked_dir),
            "sed -i -e 's/seeds: \"127.0.0.1\"/seeds: \"{seeds}\"/g' {dir}/conf/cassandra.yaml"
            .format(seeds=seeds, dir=unpacked_dir),
            "echo \"commitlog_directory: /data/cassandra/commitlog\" | tee -a {dir}/conf/cassandra.yaml"
            .format(dir=unpacked_dir),
            "sed -i -e 's/{default}/\/data\/cassandra\/log/g' {dir}/conf/logback.xml"
            .format(default="${cassandra.logdir}", dir=unpacked_dir),
            "sed -i -e 's/endpoint_snitch: SimpleSnitch/endpoint_snitch: Ec2Snitch/g' {dir}/conf/cassandra.yaml"
            .format(dir=unpacked_dir),
            "sed -i -e 's/{gc}/\/data\/cassandra\/log\/gc.log/g' {dir}/conf/cassandra-env.sh"
            .format(gc="${CASSANDRA_HOME}\/logs\/gc.log", dir=unpacked_dir),
            "sudo yum -y install java-1.8.0; sudo yum -y remove java-1.7.0-openjdk",
        ]
        command = ";".join(commands)
        ssh(public_name, args, command)
        time.sleep(10)

        print("Setting up disks and running Cassandra")
        commands = [
            # mount the storage used for storing data.
            # ** n.b. Assumes just one disk atm. **
            'sudo mkfs -t ext4 /dev/xvdt; sudo mkdir /data; sudo mount /dev/xvdt /data',
            'sudo mkdir -p /data/cassandra/data',
            'sudo mkdir -p /data/cassandra/log',
            'sudo chown -fR {user} /data/cassandra/'.format(user=args.user),
        ]
        command = ";".join(commands)
        ssh(public_name, args, command)

        print("Running Cassandra on node {dns}".format(dns=public_name))
        ssh(public_name, args, command="nohup /home/{user}/{dir}/bin/cassandra".format(user=args.user, dir=unpacked_dir))
```
## Example Output
First run the script to create the cluster, many of the options have ‘development’ defaults.
~~~
waiheke:src lewismj$ ./cassandra_ec2.py -r eu-central-1 -k amz1 -i ~/.aws/amz1.pem -m ami-f9619996 -v vpc-00x000xx -a create -n WaioekaDev1 -c 1
Creating cluster ...  WaioekaDev1 in region eu-central-1
Creating security group WaioekaDev1
Checking to see if cluster is already running...
Launching 1 instances for cluster...
Waiting for AWS to propagate instance metadata...
Waiting for cluster nodes to be 'ssh-ready'
.
Cluster is now 'ssh-ready'. Waited 146 seconds
Downloading Cassandra version 3.9
[################################] 35860/35860 - 00:01:14
Warning: Permanently added 'ec2-??-??-??-???.eu-central-1.compute.amazonaws.com,??.??.???' (ECDSA) to the list of known hosts.
building file list ... done
apache-cassandra-3.9-bin.tar.gz

sent 36724421 bytes  received 42 bytes  175295.77 bytes/sec
total size is 36719829  speedup is 1.00
Unpacking and editing configuration files.
Warning: Permanently added 'ec2-??-??-??-???.eu-central-1.compute.amazonaws.com,??.??.???' (ECDSA) to the list of known hosts.
broadcast_address: 172.31.4.81 
data_file_directories:
- /data/cassandra/data
commitlog_directory: /data/cassandra/commitlog
Complete!
Connection to ec2-??-??-??-???.eu-central-1.compute.amazonaws.com closed.
Setting up disks and running Cassandra
Warning: Permanently added 'ec2-??-??-??-???.eu-central-1.compute.amazonaws.com,??.??.???' (ECDSA) to the list of known hosts.
mke2fs 1.42.12 (29-Aug-2014)
Creating filesystem with 2097152 4k blocks and 524288 inodes
Filesystem UUID: f60a80ea-6144-4479-80f1-62d10b18a137
Superblock backups stored on blocks: 
    32768, 98304, 163840, 229376, 294912, 819200, 884736, 1605632

Allocating group tables: done                            
Writing inode tables: done                            
Creating journal (32768 blocks): done
Writing superblocks and filesystem accounting information: done 

Connection to ec2-??-??-??-???.eu-central-1.compute.amazonaws.com closed.
Running Cassandra on node ec2-??-??-??-???.eu-central-1.compute.amazonaws.com
Warning: Permanently added 'ec2-??-??-??-???.eu-central-1.compute.amazonaws.com,??.??.???' (ECDSA) to the list of known hosts.
nohup: ignoring input and appending output to ‘nohup.out’
Connection to ec2-??-??-??-???.eu-central-1.compute.amazonaws.com closed.
Cluster setup complete.
waiheke:src lewismj$
~~~

Once setup, you can check that Cassandra is running using cqlsh:

~~~
waiheke:~ lewismj$ cqlsh ec2-??-??-??-???.eu-central-1.compute.amazonaws.com -u cassandra -p cassandra
Connected to WaioekaDev1 at ec2-??-??-??-???.eu-central-1.compute.amazonaws.com:9042.
[cqlsh 5.0.1 | Cassandra 3.9 | CQL spec 3.4.2 | Native protocol v4]
Use HELP for help.
cassandra@cqlsh> exit
~~~

[1]:	https://github.com/amplab/spark-ec2
