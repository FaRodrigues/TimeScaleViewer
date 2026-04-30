# TimeScaleViewer

**TimeScaleViewer** is a software tool written in Python used by UTC(INXE) to monitor daily data sent to the TAI FTP repository. 

The software was developed to allow colaboration between Inmetro and other laboratories like LRTE (São Carlos).

The software provides a user interface to view CGGTTS data and use the same files to calculate the time drift of the respective clock relative to GNSS time and relative to UTC forecasts.
This tool incorporates an RS-232 serial control interface for the HROG-10 microphase stepper equipment manufactured by SpectraDynamics. Since the HROG-10 does not use a standard programmable interface like VISA (Virtual Instrument Software Architecture), I developed a dictionary for this software based on SpectraDynamics' proprietary commands. Additionally, TimeScaleViewer provides a decoder for the "error condition codes" of the HROG-10's weighted numeric alarm code.
It is also important to note:
1.	The software monitors the frequency offset applied to the equipment HROG-10 using the command FREQ?;
2.	The software can monitor the frequency offset scheduled to be applied to the equipment HROG-10 and set a new frequency offset using the command FREQ [freq value];
3.	The software is portable so it can be used both from a pen drive as from a web server;
4.	TimeScaleViewer can use SCP of FTP protocol, so UTC(INXE) use this software to monitor CGGTTS files uploaded to BIPM TAI;
5.	The software is cross platform and so it works on both Windows and Linux;

'''
xml
<profile labname="LRTE" commtype="SCP">
  <scpuser>cal-lrte</scpuser>
  <accesslink>tempo.inmetro.gov.br</accesslink>
  <username>cal-lrte</username>
  <password></password>
  <labid>LR</labid>
  <prefix>GZLRRO</prefix>
  <rxid>RO</rxid>
</profile>
'''

***Note: Due to security concerns, this code do not contain the full features used in laboratory***
