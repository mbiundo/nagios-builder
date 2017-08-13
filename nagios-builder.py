#!/usr/bin/python
# Importing Libraries
import argparse
import sys
import subprocess
import os
import glob
import csv
import socket
import time
# Parse Arguments
parser = argparse.ArgumentParser(description="PNSN MCSOH Nagios Builder - Python", epilog='CSV Format (* denote required field): \n     Hostname*, IP*, Model*, Longitude, Latitude, SNMP Port, HTTP Port\n\nMUST BE RUN WITH SUDO', add_help=True, formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument("-i","--input", help="CSV To Be Processed, fields", action="store", required=True)
parser.add_argument("-v","--verbose", help="increase output verbosity",action="store_true")
args = parser.parse_args()
if args.verbose:
	print "Verifying we can read the CSV File"
	print "Input: "+args.input
# Verify we can read CSV	
ret = os.access(args.input, os.R_OK)
if not ret:
	print "Could not read the file, please check the path.  Path entered: "+args.input
	exit()
# Create Backup
nagios_backup="/etc/nagios/nagios.cfg."+str(int(time.time()))
nagios_tmp="/etc/nagios/nagios.cfg."+str(int(time.time()))+".tmp"
timestamp=time.strftime('%Y-%m-%d %H:%M:%S');
if args.verbose:
	print "File successfully read."
	print "Creating nagios.cfg backup at "+nagios_backup
# Creating temporary nagios.cfg for testing	
subprocess.call("cp -avr /etc/nagios/nagios.cfg "+nagios_tmp, shell=True)
file = open(nagios_tmp,"a") 
file.write("# Updated by nagios-builder on "+timestamp+"\n")
file.close()
return_code = subprocess.call("cp -avr /etc/nagios/nagios.cfg "+nagios_backup, shell=True)
if return_code != 0:
	print "Backup Not Created, Exiting"
	exit()
if args.verbose:
	print "Backup created at "+nagios_backup
	print "Beginning to process CSV"
count=0
nagios_names=["host_name","address	","use","_longitude","_latitude","_port_snmp","_port_http"]
human_names=["Hostname (1st value)","IP Address (2nd value)","Model (3rd value)","Longitude (4th Value)","Latitude (5th Value)","SNMP Port (6th Value)","HTTP Port (7th Value)"]
with open(args.input, 'rb') as f:
    reader = csv.reader(f)
    for row in reader:
    	if not row[0].startswith('#'): # Skip lines that start with #
			count+=1
			# Checking that we have at least 3 fields (minimum required)
			if args.verbose:
				print row
				print "Found "+str(len(row))+" Fields"
			if len(row) < 3:
				print "Problem with row "+count+"; one or more required fields are missing"
			if len(row) > 7:
				print "Problem with row "+count+"; too many fields entered"
			# Listing Variables
			if args.verbose:
				for i in xrange(0,len(row)):
					print human_names[i]+" is "+row[i]
				print "Verifying values are valid"
			# Verify we have a valid IP
			try:
				socket.inet_aton(row[1])
			except socket.error:
				print row[1]+" is not a valid IPv4 address, exiting"
				exit()
			# Verify model is valid
			if not row[2] in open('models.txt').read():
				print row[2]+" is not a valid model, exiting"
				print "Please check /usr/local/pkgs/nagios-builder/models.txt for a list of valid models"
				exit()
			config_directory=glob.glob("/etc/nagios/objects/pnsnops/hosts/*/"+row[2])
			config_file=config_directory[0]+"/"+row[0]+".cfg"
			# Verify doesn't already exist        	
			if args.verbose:
				print "Checking if "+config_file+" already exists"
			if os.path.isfile(config_file):
				print "Config file already exists for this hostname, exiting"
				exit()
			# Create Config File
			if args.verbose:
				print "Creating "+config_file
			file = open(config_file,"w") 
			file.write("# Config file created by nagios-builder on "+timestamp+"\n")
			file.write("# Input file was "+args.input+"\n\n")
			file.write("define host{\n") 
			for i in xrange(0,len(row)):
				if i == 2:
					file.write("	use				"+row[2]+"-template\n")
				else:
					file.write("	"+nagios_names[i]+"		"+row[i]+"\n") 
			file.write("}\n") 
			file.close()
			# Add to tmp nagios config file
			file = open(nagios_tmp,"a") 
			file.write("cfg_file="+config_file+"\n")
			file.close()
			# Run nagios -v on tmp nagios config file
			return_code = subprocess.call("nagios -v "+nagios_tmp+"> /dev/null 2>&1", shell=True)
			if return_code != 0:
				print "Nagios verification failed; exiting"
				print "The check may be manually ran using \"nagios -v "+nagios_tmp+"\" "
				exit()
# Run final nagios -v check
return_code = subprocess.call("nagios -v "+nagios_tmp+" > /dev/null 2>&1", shell=True)
if return_code != 0:
	print "Nagios verification failed; exiting"
	print "The check may be manually ran using \"nagios -v "+nagios_tmp+"\" "
	exit()
if args.verbose:
	print "All Nagios checks have passed, activating new config file and restarting"
# Move tmp nagios to live nagios
return_code = subprocess.call("mv "+nagios_tmp+" /etc/nagios/nagios.cfg", shell=True)
if return_code != 0:
	print "Something went wrong with moving nagios.cfg, please alert Marc Biundo (mbiundo@uw.edu) and CompHelp (comphelp@ess.washington.edu)"
	exit()
# Restart nagios 
subprocess.call("systemctl restart nagios", shell=True)
# Check status, if not 0 rollback
nagios_return_code = subprocess.call("systemctl status nagios > /dev/null 2>&1", shell=True)
if nagios_return_code !=0:
	print "Nagios failed to start, rolling back."
	return_code = subprocess.call("/usr/bin/cp -avr "+nagios_backup+" /etc/nagios/nagios.cfg", shell=True)
	if return_code != 0:
		print "Something went wrong with moving nagios.cfg, please alert Marc Biundo (mbiundo@uw.edu) and CompHelp (comphelp@ess.washington.edu)"
	else:
		subprocess.call("systemctl restart nagios", shell=True)
	return_code = subprocess.call("systemctl status nagios > /dev/null 2>&1", shell=True)
	if return_code != 0:
		print "Something went wrong with moving nagios.cfg, please alert Marc Biundo (mbiundo@uw.edu) and CompHelp (comphelp@ess.washington.edu)"
	else:
		print "Rollback successful"
	exit()
# Send Email ($USER tells who ran it)
subprocess.call("echo -e \"Timestamp: "+timestamp+"\nUsername: "+os.environ['SUDO_USER']+"\nNagios Status: "+str(nagios_return_code)+" - # 0 = Running, 3 = Stopped, Others are bad\nNagios Diff File: "+nagios_backup+"\nRow Count: "+str(count)+"\" | mailx -s \"nagios-builder on rachel "+timestamp+"\" -a \""+args.input+"\" mbiundo@uw.edu,comphelp@ess.washington.edu,pnsncomp@uw.edu ", shell=True)
# Output all done message
print "nagios-builder has completed successfully and hosts should appear in the web view momentarily"