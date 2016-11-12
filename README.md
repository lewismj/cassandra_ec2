# Cassandra EC2
This repository provides some simple Python scripts for creating an Apache Cassandra cluster using EC2 instances. Useful if you want to spin up a development cluster using script, without relying on DCOS or similar.

I’ve taken some things from the [SparkEC2][1]project.

*Under development, currently just the ‘create’ action is supported.*

### Todo

- [ ]() implement the destroy command.
- [ ]() make the options a configuration file.
- [ ]() more customisation of the ```cassandra.yaml``` file is required (e.g. changing the Snitch setting etc…).

### Name
**```cassandra_ec2.py [options] ```**

### Description
Briefly, this script will:

- create a security group.
- launch the desired number of instances, with storage.
- wait for the cluster to start (i.e. can ‘ssh’ to the instances).
- download the desired version of Apache Cassandra.
- copy Cassandra to each instance.
- perform a number of ‘sed’ edits on each ‘cassandra.yaml’ file.

### Options

- **-u —user** The SSH user you want to connect to your instances as (default: ec2-user).
- **-r —region** EC2 region name (default: eu-central-1).
- **-z —zone** The availability zone to use (default: eu-central-1b).
- **-i —identity-file** SSH private key 
- **-k —key-pair** The key-pair name to use on instances.
- **-t —instance-type** Instance type of instance to launch (default: m1.large).
- **-m** *—ami* Amazon machine image ID to use.
- **-s —ebs-vol-size** Size (in GB) of each EBS volume (default: 8GB).
- **-e —ebs-vol-type** EBS volume type, e.g. ‘gp2’ (default: standard).
- **-d —authorized-address** Address to authorise on created security groups (default: 0.0.0.0/0).
- **-v —vpc-id** VPC id of VPC to launch instance in.
- **-c —node-count** Number of nodes to create for the cluster.
- **-a —action** The action to perform (‘create’, ‘destroy’).
- **-n —name** The name of the cluster.
- **-o —version** The version of Cassandra to deploy.

[1]:	https://github.com/amplab/spark-ec2
