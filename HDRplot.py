import os
import subprocess
import re
import json
from vapoursynth import core
import awsmfunc as awf
from pymediainfo import MediaInfo
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from colorama import init as colorama_init
from colorama import Fore
from colorama import Style


def HDRplot(
    path: str,
    fileIdentifier: str = "DEFAULT",
    title: str = None,
    left: int = 0,
    right: int = 0,
    top: int = 0,
    bottom: int = 0,
    trimStart: int = 0,
    trimEnd: int = 0,
    L1: bool = False
):
    """
    Plot the brightness of each frame of a HDR/DV hevc/hevc video file.
    This function will create a .png file with the plot.
    Relevant information from the mediainfo and the RPU file are extracted and added to the plot.
    In case of a DV P5 file, the clip will be first tonemapped to HDR.
    At first run on a file, the CLL/FALL values of each frame are measured (can take several hours) and stored
    in a .json file, to be possibly reused.
    Can also plot the L1 metadata contained in the DoVi RPU file.

    :param path: relative path to the video file (accepts absolute path)
    :param fileIdentifier: tag for the filenames lightLevel-tag.json and HDRplot-tag.png
    :param title: optional title for the plot. If missing a default title with the name of the video file will be used
    :param left: crop value
    :param right: crop value
    :param top: crop value
    :param bottom: crop value
    :param trimStart: number of frames to trim at the start of the clip for plotting (useful to sync plots between clips with different numbers of frame)
    :param trimEnd: number ot frames to trim at the end
    :param L1: whether to plot HDR grade of L1 metadata from the RPY file
    """


    #----------------#
    # Initialization #
    #----------------#

    colorama_init()

    videoFile = os.path.abspath(path)
    if not os.path.exists(videoFile):
        print(f"{Fore.RED}Video file{Style.RESET_ALL}  {path} {Fore.RED}not found.{Style.RESET_ALL}")
        return

    media_info = MediaInfo.parse(videoFile)
    mdcp = None
    mdlMin = None
    profile = None
    version = None
    subTitleHDR1 = None
    subTitleHDR2 = None
    subTitleDV1 = None
    subTitleDV2 = None

    hdrFormat = media_info.video_tracks[0].hdr_format
    if hdrFormat != "Dolby Vision / SMPTE ST 2086" and hdrFormat != "Dolby Vision" and hdrFormat != "SMPTE ST 2086":
        print(f"{Fore.RED}HDR format not recognized.{Style.RESET_ALL}")
        return
    if hdrFormat == "Dolby Vision / SMPTE ST 2086" or hdrFormat == "SMPTE ST 2086":
        mdcp = media_info.video_tracks[0].mastering_display_color_primaries
        mdlMin = media_info.video_tracks[0].mastering_display_luminance[5:11]
        mdlMax = media_info.video_tracks[0].mastering_display_luminance[24:28]
    if hdrFormat == "Dolby Vision / SMPTE ST 2086" or hdrFormat == "Dolby Vision":
        command = ['ffmpeg -i ' + "'" + videoFile + "'" + ' -c:v copy -bsf:v hevc_mp4toannexb -f hevc - | dovi_tool extract-rpu -o RPU-temp.bin -']
        subprocess.run(command, shell=True)
        result = subprocess.run('dovi_tool info -s RPU-temp.bin', stdout=subprocess.PIPE, shell=True)
        doviSummary = [x.strip() for x in result.stdout.decode().split('\n')]
        if L1:
            subprocess.run('dovi_tool export -i RPU-temp.bin -d all=RPU-temp.json', shell=True)
            with open('RPU-temp.json') as file:
                RPU = json.load(file)
            subprocess.run('rm RPU-temp.json', shell=True)
        subprocess.run('rm RPU-temp.bin', shell=True)
        for line in doviSummary:
            if 'RPU mastering display' in line:
                subTitleDV2 = line
            if 'Profile' in line:
                profile = line
            if 'DM version' in line:
                version = line
        if profile is not None and version is not None:
            profile = re.sub(":", "", profile)
            version = re.sub(r'.*\(', '', version)
            version = re.sub(r'\)', '', version)
            subTitleDV1 = 'Dolby Vision ' + profile + ', ' + version
    if mdcp is not None:
        subTitleHDR1 = "Mastering Display Color Primaries: " + mdcp
    if mdlMin is not None:
        subTitleHDR2 = "Mastering Display Luminance: " + mdlMin + "/" + mdlMax + " nits"
    if subTitleHDR1 is None and subTitleHDR2 is not None:
        subTitleHDR1 = ""
    if subTitleHDR2 is None and subTitleHDR1 is not None:
        subTitleHDR2 = ""
    if subTitleHDR1 is None and subTitleHDR2 is None:
        subTitleHDR1 = ""
        subTitleHDR2 = "No HDR metadata in original file"
    if subTitleDV1 is None and subTitleDV2 is not None:
        subTitleDV1 = ""
    if subTitleDV2 is None and subTitleDV1 is not None:
        subTitleDV2 = ""
    if subTitleDV1 is None and subTitleDV2 is None:
        subTitleDV1 = ""
        subTitleDV2 = "No Dolby Vision"

    src = core.ffms2.Source(videoFile)

    if left < 0 or right < 0 or top < 0 or bottom < 0 or left % 2 !=0  or right % 2 !=0  or top % 2 !=0  or bottom % 2 !=0:
        print(f"{Fore.RED}Incorrect cropping values.{Style.RESET_ALL}")
        return

    if trimStart < 0 or trimStart+trimEnd > len(src):
        print(f"{Fore.RED}Incorrect trim values.{Style.RESET_ALL}")
        return


    if title is None:
        title = "HDR grade: " + path

    HDRclip = core.std.Crop(src, left=left, right=right, top=top, bottom=bottom)

    filename = 'lightLevel-' + fileIdentifier + '.json'
    jsonFile = os.path.abspath(filename)

    if L1:
        HDRMax = []
        HDRFALL = []
        for frame in range(len(HDRclip)):
            max_pq = RPU[frame]["vdr_dm_data"]["cmv29_metadata"]['ext_metadata_blocks'][0]["Level1"]["max_pq"]
            avg_pq = RPU[frame]["vdr_dm_data"]["cmv29_metadata"]['ext_metadata_blocks'][0]["Level1"]["avg_pq"]
            max_nits = awf.st2084_eotf(float(max_pq/4095)) * 10000
            avg_nits = awf.st2084_eotf(float(avg_pq/4095)) * 10000
            HDRMax.append(max_nits)
            HDRFALL.append(avg_nits)
        lightLevel = [HDRMax, HDRFALL]
    elif os.path.exists(jsonFile):
        with open(jsonFile) as f:
            lightLevel = json.load(f)
    else:
        # No json file containing the lightLevel data. We have to measure.
        if hdrFormat == hdrFormat == "Dolby Vision":
            # DoVi P5 video. We have to tonemap to HDR before measuring.
            HDRclip = awf.Depth(HDRclip, 16)
            HDRclip = core.placebo.Tonemap(HDRclip, src_csp = 3, dst_csp = 1)
            HDRclip = core.resize.Spline36(HDRclip, range_s="limited", range_in_s="full", dither_type="error_diffusion")
            HDRclip = awf.Depth(HDRclip, 10)

        #------------------------------------------------------------#
        # Extract HDR data from clip and store them in a double list #
        #------------------------------------------------------------#

        HDRclip = awf.add_hdr_measurement_props(HDRclip,as_nits=True,percentile=99.99,downscale=False,hlg=False,max_luminance=False,no_planestats=True,compute_hdr10plus=False,linearized=True)

        # HDRclip = core.text.FrameProps(HDRclip)  # this part is meant to show the HDR data in vs-preview
        # if vspreview.is_preview():
        #     set_output(HDRclip)

        HDRMax = []
        HDRFALL = []
        for frame in range(len(HDRclip)):
            HDRMax.append(HDRclip.get_frame(frame).props['HDRMax'])
            HDRFALL.append(HDRclip.get_frame(frame).props['HDRFALL'])
            print(f"\rMeasuring brightness of frame {Fore.BLUE}{frame}{Style.RESET_ALL} out of {len(HDRclip)}...",end='')

        lightLevel = [HDRMax, HDRFALL]

        # Write HDR data to file for possible reuse
        with open(jsonFile, 'w') as f:
            json.dump(lightLevel, f)

    #------------------------------------------#
    # Trim HDR metada in view of sync'ing them #
    #------------------------------------------#

    start = trimStart
    end = len(HDRclip) - trimEnd
    lightLevel[0] = lightLevel[0][start:end]
    lightLevel[1] = lightLevel[1][start:end]


    #------------------------------------------#
    # Compute max and average values from data #
    #------------------------------------------#

    maxCLL = round(max(lightLevel[0]),2)
    maxFALL = round(max(lightLevel[1]),2)
    avgCLL = round(sum(lightLevel[0])/len(lightLevel[0]),2)
    avgFALL = round(sum(lightLevel[1])/len(lightLevel[1]),2)

    CLLpq = [awf.st2084_inverse_eotf(x) for x in lightLevel[0]]
    FALLpq = [awf.st2084_inverse_eotf(x) for x in lightLevel[1]]

    maxCLLpq = round(awf.st2084_eotf(np.percentile(CLLpq, 99.5)) * 10000,2)
    maxFALLpq = round(awf.st2084_eotf(np.percentile(FALLpq, 99.75)) * 10000,2)


    #---------------#
    # Draw the plot #
    #---------------#

    fig, ax = plt.subplots(figsize=(18, 7.2))
    ax.plot(lightLevel[0], color='royalblue', lw=0.3)
    ax.plot(lightLevel[1], color='blueviolet', lw=0.3)
    frames = range(len(lightLevel[0]))
    ax.fill_between(frames, lightLevel[0], lightLevel[1], color='royalblue', alpha=0.4)
    ax.fill_between(frames, lightLevel[1], 0.1, color='blueviolet', alpha=0.4)
    plt.grid(True, which ="both",color='black',lw=0.1)
    plt.semilogy()
    ax.set_title(title, fontsize=16,pad=70)
    ax.set_xlabel("frames", fontsize=10, labelpad=8.0)
    ax.set_ylabel("nits (cd/m${}^2$)", fontsize=10, labelpad=3.0)
    ax.axis([0, len(lightLevel[0]), 0.1, 5000.0])
    ax.xaxis.set_major_locator(mpl.ticker.LinearLocator(numticks=20))
    ax.yaxis.set_major_locator(mpl.ticker.LogLocator(base=1.001, numticks=20))
    # f1 = mpl.ticker.ScalarFormatter()
    # f1 = mpl.ticker.StrMethodFormatter("{x:.3g}")
    # f1.set_scientific(False)
    # ax.yaxis.set_major_formatter(f1)
    yTicks = [np.format_float_positional(float(x),precision=max(1 - int(np.ceil(np.log10(float(x)))), 0),trim="-",) for x in ax.get_yticks()]
    ax.set_yticklabels(yTicks)
    # ax.spines["top"].set_linewidth(0)
    # ax.spines["right"].set_linewidth(0)
    cll = "CLL"
    fall = "FALL"
    legend = plt.legend([f"{cll:<7}(maxCLL  = {maxCLLpq:8.2f} nits,  avgCLL  = {avgCLL:8.2f} nits.)", f"{fall:<6}(maxFALL = {maxFALLpq:8.2f} nits,  avgFALL = {avgFALL:8.2f} nits.)"], loc="lower left", fontsize=12)
    legend.get_frame().set_alpha(None)
    for line in legend.get_lines():
        line.set_linewidth(2.0)
    # xmin, xmax = ax.get_xlim()
    plt.text(0, 1.020, subTitleHDR2,ha='left', va='bottom',transform=ax.transAxes,fontsize=12)
    plt.text(0, 1.070, subTitleHDR1,ha='left', va='bottom',transform=ax.transAxes,fontsize=12)
    plt.text(1, 1.020, subTitleDV2,ha='right', va='bottom',transform=ax.transAxes,fontsize=12)
    plt.text(1, 1.070, subTitleDV1,ha='right', va='bottom',transform=ax.transAxes,fontsize=12)
    plt.tight_layout(pad=0.7)

    plt.savefig('HDRplot-' + fileIdentifier + '.png')
    plt.show()
    plt.close()

    return
