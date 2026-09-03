#include <AudioToolbox/AudioToolbox.h>
#include <rubberband/RubberBandStretcher.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <iostream>
#include <mutex>
#include <regex>
#include <string>
#include <thread>
#include <vector>

using RubberBand::RubberBandStretcher;

struct Player {
    static constexpr UInt32 block = 1024;
    AudioQueueRef queue{};
    std::vector<float> audio;
    UInt32 rate = 48000, channels = 2;
    std::atomic<size_t> sourceFrame{0};
    std::atomic<bool> playing{false}, resetRequested{false};
    std::atomic<double> seekSeconds{-1}, tempo{1}, pitch{1}, volume{1}, mrGain{1}, melodyGain{0}, vocalGain{0};
    std::vector<float> guide, vocals;
    std::unique_ptr<RubberBandStretcher> rb;
    std::vector<float> left, right, outLeft, outRight;

    bool load(const std::string &path) {
        playing = false;
        if (queue) { AudioQueueStop(queue, true); AudioQueueDispose(queue, true); queue = nullptr; }
        CFURLRef url = CFURLCreateFromFileSystemRepresentation(nullptr, (const UInt8 *)path.c_str(), path.size(), false);
        ExtAudioFileRef file{};
        if (ExtAudioFileOpenURL(url, &file) != noErr) { CFRelease(url); return false; }
        CFRelease(url);
        AudioStreamBasicDescription src{}; UInt32 n = sizeof(src);
        ExtAudioFileGetProperty(file, kExtAudioFileProperty_FileDataFormat, &n, &src);
        rate = UInt32(src.mSampleRate); channels = 2;
        SInt64 frames = 0; n = sizeof(frames);
        ExtAudioFileGetProperty(file, kExtAudioFileProperty_FileLengthFrames, &n, &frames);
        AudioStreamBasicDescription fmt{double(rate), kAudioFormatLinearPCM,
            kAudioFormatFlagsNativeFloatPacked, 8, 1, 8, 2, 32, 0};
        ExtAudioFileSetProperty(file, kExtAudioFileProperty_ClientDataFormat, sizeof(fmt), &fmt);
        audio.resize(size_t(frames) * 2);
        AudioBufferList list{}; list.mNumberBuffers = 1; list.mBuffers[0] = {2, UInt32(audio.size() * sizeof(float)), audio.data()};
        UInt32 count = UInt32(frames);
        bool ok = ExtAudioFileRead(file, &count, &list) == noErr;
        ExtAudioFileDispose(file); audio.resize(size_t(count) * 2); sourceFrame = 0;
        guide.clear(); vocals.clear();
        auto loadTrack = [&](std::string trackPath, std::vector<float> &track) {
            CFURLRef trackUrl = CFURLCreateFromFileSystemRepresentation(nullptr, (const UInt8 *)trackPath.c_str(), trackPath.size(), false);
            ExtAudioFileRef trackFile{};
            if (ExtAudioFileOpenURL(trackUrl, &trackFile) == noErr) {
                SInt64 trackFrames=0; n=sizeof(trackFrames); ExtAudioFileGetProperty(trackFile,kExtAudioFileProperty_FileLengthFrames,&n,&trackFrames);
                ExtAudioFileSetProperty(trackFile,kExtAudioFileProperty_ClientDataFormat,sizeof(fmt),&fmt);
                track.resize(size_t(trackFrames)*2); AudioBufferList tl{}; tl.mNumberBuffers=1; tl.mBuffers[0]={2,UInt32(track.size()*sizeof(float)),track.data()};
                UInt32 tc=UInt32(trackFrames); if(ExtAudioFileRead(trackFile,&tc,&tl)!=noErr) track.clear(); else track.resize(size_t(tc)*2);
                ExtAudioFileDispose(trackFile);
            }
            CFRelease(trackUrl);
        };
        auto marker = path.rfind("_mr.wav");
        if (marker != std::string::npos) {
            loadTrack(path.substr(0, marker) + "_guide.wav", guide);
            loadTrack(path.substr(0, marker) + "_guide_vocals.wav", vocals);
        }
        rb = std::make_unique<RubberBandStretcher>(rate, 2,
            RubberBandStretcher::OptionProcessRealTime | RubberBandStretcher::OptionEngineFiner);
        rb->setMaxProcessSize(block); left.resize(block); right.resize(block); outLeft.resize(block); outRight.resize(block);
        if (AudioQueueNewOutput(&fmt, callback, this, nullptr, nullptr, 0, &queue) != noErr) return false;
        for (int i = 0; i < 3; ++i) { AudioQueueBufferRef b; AudioQueueAllocateBuffer(queue, block * 2 * sizeof(float), &b); fill(b); AudioQueueEnqueueBuffer(queue, b, 0, nullptr); }
        AudioQueueStart(queue, nullptr); return ok;
    }

    static void callback(void *p, AudioQueueRef q, AudioQueueBufferRef b) {
        auto *self = static_cast<Player *>(p); self->fill(b); AudioQueueEnqueueBuffer(q, b, 0, nullptr);
    }

    void fill(AudioQueueBufferRef b) {
        float *dst = static_cast<float *>(b->mAudioData); std::fill(dst, dst + block * 2, 0.f);
        if (!rb || !playing) { b->mAudioDataByteSize = block * 2 * sizeof(float); return; }
        double seek = seekSeconds.exchange(-1);
        if (seek >= 0) { sourceFrame = std::min(size_t(seek * rate), audio.size() / 2); resetRequested = true; }
        if (resetRequested.exchange(false)) rb->reset();
        rb->setTimeRatio(1.0 / tempo.load()); rb->setPitchScale(pitch.load());
        size_t written = 0;
        while (written < block) {
            int available = rb->available();
            if (available > 0) {
                float *outs[]{outLeft.data(), outRight.data()};
                size_t got = rb->retrieve(outs, std::min<size_t>(available, block - written));
                float gain = float(volume.load());
                for (size_t i = 0; i < got; ++i) { dst[(written+i)*2] = outLeft[i]*gain; dst[(written+i)*2+1] = outRight[i]*gain; }
                written += got; continue;
            }
            size_t pos = sourceFrame.load(), total = audio.size() / 2;
            if (pos >= total) { playing = false; break; }
            size_t count = std::min<size_t>({block, total-pos, rb->getSamplesRequired()});
            if (!count) count = std::min<size_t>(block, total-pos);
            float mr=float(mrGain.load()), mg=float(melodyGain.load()), vg=float(vocalGain.load());
            for (size_t i=0;i<count;++i) {
                size_t j=(pos+i)*2;
                left[i]=audio[j]*mr + (j < guide.size() ? guide[j]*mg : 0.f) + (j < vocals.size() ? vocals[j]*vg : 0.f);
                right[i]=audio[j+1]*mr + (j+1 < guide.size() ? guide[j+1]*mg : 0.f) + (j+1 < vocals.size() ? vocals[j+1]*vg : 0.f);
            }
            const float *ins[]{left.data(), right.data()}; rb->process(ins, count, pos+count>=total); sourceFrame = pos+count;
        }
        b->mAudioDataByteSize = block * 2 * sizeof(float);
    }

    double duration() const { return rate ? double(audio.size()/2)/rate : 0; }
    double position() const { return rate ? double(sourceFrame.load())/rate : 0; }
};

static std::string str(const std::string &s, const char *key) {
    std::smatch m; std::regex r(std::string("\\\"")+key+"\\\"\\s*:\\s*\\\"([^\\\"]+)\\\""); return std::regex_search(s,m,r)?m[1].str():"";
}
static double num(const std::string &s, const char *key, double fallback) {
    std::smatch m; std::regex r(std::string("\\\"")+key+"\\\"\\s*:\\s*(-?[0-9.]+)"); return std::regex_search(s,m,r)?std::stod(m[1].str()):fallback;
}
int main() {
    Player p; std::string line;
    while (std::getline(std::cin,line)) {
        auto cmd=str(line,"cmd"); bool ok=true;
        if(cmd=="load") ok=p.load(str(line,"path"));
        else if(cmd=="play") p.playing=true;
        else if(cmd=="pause") p.playing=false;
        else if(cmd=="seek") p.seekSeconds=num(line,"position",p.position());
        else if(cmd=="params") { double key=std::clamp(num(line,"key",0.),-7.,7.); p.pitch=std::pow(2.,key/12.); p.tempo=std::clamp(num(line,"tempo",1.),.5,2.); p.volume=std::clamp(num(line,"volume",1.),0.,1.); p.mrGain=std::clamp(num(line,"mr",1.),0.,2.); p.melodyGain=std::clamp(num(line,"melody",0.),0.,2.); p.vocalGain=std::clamp(num(line,"vocal",0.),0.,2.); }
        else if(cmd!="state") ok=false;
        std::cout << "{\"ok\":"<<(ok?"true":"false")<<",\"playing\":"<<(p.playing?"true":"false")<<",\"position\":"<<p.position()<<",\"duration\":"<<p.duration()<<",\"volume\":"<<p.volume<<",\"mr\":"<<p.mrGain<<",\"melody\":"<<p.melodyGain<<",\"vocal\":"<<p.vocalGain<<",\"guideLoaded\":"<<(!p.guide.empty()?"true":"false")<<",\"vocalsLoaded\":"<<(!p.vocals.empty()?"true":"false")<<"}" << std::endl;
    }
}
