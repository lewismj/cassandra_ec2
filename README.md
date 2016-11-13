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

...
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
Loaded plugins: priorities, update-motd, upgrade-helper
amzn-main/latest                                                                                                                       | 2.1 kB     00:00     
amzn-updates/latest                                                                                                                    | 2.3 kB     00:00     
Resolving Dependencies
--> Running transaction check
---> Package java-1.8.0-openjdk.x86_64 1:1.8.0.111-1.b15.25.amzn1 will be installed
--> Processing Dependency: java-1.8.0-openjdk-headless = 1:1.8.0.111-1.b15.25.amzn1 for package: 1:java-1.8.0-openjdk-1.8.0.111-1.b15.25.amzn1.x86_64
--> Running transaction check
---> Package java-1.8.0-openjdk-headless.x86_64 1:1.8.0.111-1.b15.25.amzn1 will be installed
amzn-main/latest/filelists_db                                                                                                          | 5.1 MB     00:00     
amzn-updates/latest/filelists_db                                                                                                       | 1.0 MB     00:00     
--> Processing Dependency: lksctp-tools for package: 1:java-1.8.0-openjdk-headless-1.8.0.111-1.b15.25.amzn1.x86_64
--> Running transaction check
---> Package lksctp-tools.x86_64 0:1.0.10-7.7.amzn1 will be installed
--> Finished Dependency Resolution

Dependencies Resolved

==============================================================================================================================================================
 Package                                        Arch                      Version                                       Repository                       Size
==============================================================================================================================================================
Installing:
 java-1.8.0-openjdk                             x86_64                    1:1.8.0.111-1.b15.25.amzn1                    amzn-updates                    227 k
Installing for dependencies:
 java-1.8.0-openjdk-headless                    x86_64                    1:1.8.0.111-1.b15.25.amzn1                    amzn-updates                     39 M
 lksctp-tools                                   x86_64                    1.0.10-7.7.amzn1                              amzn-main                        89 k

Transaction Summary
==============================================================================================================================================================
Install  1 Package (+2 Dependent packages)

Total download size: 39 M
Installed size: 102 M
Downloading packages:
(1/3): java-1.8.0-openjdk-1.8.0.111-1.b15.25.amzn1.x86_64.rpm                                                                          | 227 kB     00:00     
(2/3): java-1.8.0-openjdk-headless-1.8.0.111-1.b15.25.amzn1.x86_64.rpm                                                                 |  39 MB     00:01     
(3/3): lksctp-tools-1.0.10-7.7.amzn1.x86_64.rpm                                                                                        |  89 kB     00:00     
--------------------------------------------------------------------------------------------------------------------------------------------------------------
Total                                                                                                                          19 MB/s |  39 MB  00:00:02     
Running transaction check
Running transaction test
Transaction test succeeded
Running transaction
  Installing : lksctp-tools-1.0.10-7.7.amzn1.x86_64                                                                                                       1/3 
  Installing : 1:java-1.8.0-openjdk-headless-1.8.0.111-1.b15.25.amzn1.x86_64                                                                              2/3 
  Installing : 1:java-1.8.0-openjdk-1.8.0.111-1.b15.25.amzn1.x86_64                                                                                       3/3 
  Verifying  : lksctp-tools-1.0.10-7.7.amzn1.x86_64                                                                                                       1/3 
  Verifying  : 1:java-1.8.0-openjdk-1.8.0.111-1.b15.25.amzn1.x86_64                                                                                       2/3 
  Verifying  : 1:java-1.8.0-openjdk-headless-1.8.0.111-1.b15.25.amzn1.x86_64                                                                              3/3 

Installed:
  java-1.8.0-openjdk.x86_64 1:1.8.0.111-1.b15.25.amzn1                                                                                                        

Dependency Installed:
  java-1.8.0-openjdk-headless.x86_64 1:1.8.0.111-1.b15.25.amzn1                             lksctp-tools.x86_64 0:1.0.10-7.7.amzn1                            

Complete!
Loaded plugins: priorities, update-motd, upgrade-helper
Existing lock /var/run/yum.pid: another copy is running as pid 2709.
Another app is currently holding the yum lock; waiting for it to exit...
  The other application is: yum
    Memory :  41 M RSS (283 MB VSZ)
    Started: Sun Nov 13 03:59:14 2016 - 00:00 ago
    State  : Running, pid: 2709
Resolving Dependencies
--> Running transaction check
---> Package java-1.7.0-openjdk.x86_64 1:1.7.0.111-2.6.7.2.68.amzn1 will be erased
--> Finished Dependency Resolution

Dependencies Resolved

==============================================================================================================================================================
 Package                                 Arch                        Version                                             Repository                      Size
==============================================================================================================================================================
Removing:
 java-1.7.0-openjdk                      x86_64                      1:1.7.0.111-2.6.7.2.68.amzn1                        installed                       90 M

Transaction Summary
==============================================================================================================================================================
Remove  1 Package

Installed size: 90 M
Downloading packages:
Running transaction check
Running transaction test
Transaction test succeeded
Running transaction
  Erasing    : 1:java-1.7.0-openjdk-1.7.0.111-2.6.7.2.68.amzn1.x86_64                                                                                     1/1 
  Verifying  : 1:java-1.7.0-openjdk-1.7.0.111-2.6.7.2.68.amzn1.x86_64                                                                                     1/1 

Removed:
  java-1.7.0-openjdk.x86_64 1:1.7.0.111-2.6.7.2.68.amzn1                                                                                                      

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

[1]:	https://github.com/amplab/spark-ec2
