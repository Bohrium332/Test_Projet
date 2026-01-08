#!/usr/bin/env python3
import argparse, time, struct, sys
import serial

MAGIC = b"\x55\xAA"
VER   = 1

TYPE_HELLO      = 0x02
TYPE_HELLO_ACK  = 0x03
TYPE_DATA       = 0x01
TYPE_SETBAUD    = 0x10
TYPE_SETBAUD_ACK= 0x11
TYPE_STATS_REQ  = 0x20
TYPE_STATS_RSP  = 0x21

def crc16_ccitt(data: bytes, poly=0x1021, init=0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc & 0xFFFF

def pack_frame(ftype: int, seq: int, payload: bytes) -> bytes:
    header = struct.pack("<2sBBIH", MAGIC, VER, ftype, seq, len(payload))
    body = struct.pack("<BBIH", VER, ftype, seq, len(payload)) + payload
    c = crc16_ccitt(body)
    return header + payload + struct.pack("<H", c)

class FrameParser:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes):
        self.buf.extend(data)

    def pop_one(self):
        while True:
            if len(self.buf) < 2:
                return None
            idx = self.buf.find(MAGIC)
            if idx < 0:
                self.buf.clear()
                return None
            if idx > 0:
                del self.buf[:idx]
            if len(self.buf) < 2 + 1 + 1 + 4 + 2:
                return None
            _, ver, ftype, seq, ln = struct.unpack_from("<2sBBIH", self.buf, 0)
            if ver != VER:
                del self.buf[:2]
                continue
            total_len = 2 + 1 + 1 + 4 + 2 + ln + 2
            if len(self.buf) < total_len:
                return None
            payload = bytes(self.buf[2 + 1 + 1 + 4 + 2 : 2 + 1 + 1 + 4 + 2 + ln])
            recv_crc = struct.unpack_from("<H", self.buf, 2 + 1 + 1 + 4 + 2 + ln)[0]
            body = struct.pack("<BBIH", ver, ftype, seq, ln) + payload
            ok = (recv_crc == crc16_ccitt(body))
            del self.buf[:total_len]
            return (ftype, seq, payload, ok)

def set_serial(ser: serial.Serial, baud: int):
    ser.baudrate = baud
    ser.reset_input_buffer()
    ser.reset_output_buffer()

def wait_for(parser, ser, want_type, timeout=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        data = ser.read(4096)
        if data:
            parser.feed(data)
            while True:
                fr = parser.pop_one()
                if fr is None:
                    break
                ftype, seq, payload, ok = fr
                if ok and ftype == want_type:
                    return payload
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud-list", default="1500000,2000000")
    ap.add_argument("--payload-bytes", type=int, default=240, help="payload size per DATA frame")
    ap.add_argument("--num-packets", type=int, default=500, help="number of packets to send per baud")
    ap.add_argument("--test-seconds", type=int, default=10, help="duration per baud test (unused when using num-packets)")
    ap.add_argument("--loss-threshold", type=float, default=0.1, help="max acceptable loss%% per window avg (default 0.1%%)")
    args = ap.parse_args()

    baud_list = [int(x) for x in args.baud_list.split(",") if x.strip()]
    ser = serial.Serial(args.port, baudrate=baud_list[0], timeout=0.02)
    parser = FrameParser()

    # Step1: handshake by scanning bauds
    locked_baud = None
    for b in baud_list:
        set_serial(ser, b)
        sys.stdout.write(f"[{time.strftime('%F %T')}] Try HELLO at baud={b}...\n")
        sys.stdout.flush()
        # burst HELLO
        t_end = time.time() + 0.6
        while time.time() < t_end:
            ser.write(pack_frame(TYPE_HELLO, 0, b"HELLO"))
            time.sleep(0.01)
            payload = wait_for(parser, ser, TYPE_HELLO_ACK, timeout=0.05)
            if payload and len(payload) >= 4:
                rb = struct.unpack("<I", payload[:4])[0]
                locked_baud = rb
                break
        if locked_baud is not None:
            break

    if locked_baud is None:
        print("[FATAL] handshake failed. Check wiring/GND/RS485 direction control.")
        sys.exit(1)

    sys.stdout.write(f"[{time.strftime('%F %T')}] LOCKED with slave at baud={locked_baud}\n")
    sys.stdout.flush()

    def set_baud_both(newb: int) -> bool:
        # send SETBAUD, wait ACK, then switch local
        ser.write(pack_frame(TYPE_SETBAUD, 0, struct.pack("<I", newb)))
        payload = wait_for(parser, ser, TYPE_SETBAUD_ACK, timeout=0.5)
        if not payload or len(payload) < 4:
            return False
        ackb = struct.unpack("<I", payload[:4])[0]
        if ackb != newb:
            return False
        ser.flush()
        time.sleep(0.02)
        set_serial(ser, newb)
        # quick re-HELLO to confirm
        ser.write(pack_frame(TYPE_HELLO, 0, b"HELLO"))
        payload2 = wait_for(parser, ser, TYPE_HELLO_ACK, timeout=0.4)
        return bool(payload2 and len(payload2) >= 4)

    best = None  # (baud, avg_loss)
    seq = 0

    for b in baud_list:
        sys.stdout.write(f"\n[{time.strftime('%F %T')}] === TEST baud={b} ===\n")
        sys.stdout.flush()
        if not set_baud_both(b):
            sys.stdout.write(f"[{time.strftime('%F %T')}] switch to {b} FAILED\n")
            sys.stdout.flush()
            continue

        payload = bytes((i & 0xFF for i in range(args.payload_bytes)))
        tx_frames = 0

        # 分5次发送，每次发送100个包
        packets_per_batch = args.num_packets // 5
        sys.stdout.write(f"[{time.strftime('%F %T')}] Sending {args.num_packets} packets at baud={b} in 5 batches...\n")
        sys.stdout.flush()
        
        for batch in range(5):
            for _ in range(packets_per_batch):
                ser.write(pack_frame(TYPE_DATA, seq, payload))
                seq = (seq + 1) & 0xFFFFFFFF
                tx_frames += 1
            # 每批次之间暂停一下
            time.sleep(0.2)
        
        # 等待接收完成
        time.sleep(0.3)
        
        # 请求统计信息
        ser.write(pack_frame(TYPE_STATS_REQ, 0, b""))
        rsp = wait_for(parser, ser, TYPE_STATS_RSP, timeout=0.5)
        
        if rsp and len(rsp) >= struct.calcsize("<IIIIIfIIIIIf"):
            (win_ok, win_miss, win_bad, win_dup, win_bytes, loss_win,
             total_ok, total_miss, total_bad, total_dup, _pad, loss_total) = struct.unpack("<IIIIIfIIIIIf", rsp[:struct.calcsize("<IIIIIfIIIIIf")])

            sys.stdout.write(
                f"[{time.strftime('%F %T')}] baud={b}  TX_frames={tx_frames}  "
                f"RX_ok={total_ok} miss={total_miss} bad={total_bad} dup={total_dup}  "
                f"loss_rate={loss_total:.3f}%\n"
            )
            sys.stdout.flush()
            avg_loss = float(loss_total)
        else:
            sys.stdout.write(f"[{time.strftime('%F %T')}] baud={b}  stats timeout (possible communication issue)\n")
            sys.stdout.flush()
            avg_loss = 100.0
        sys.stdout.write(f"[{time.strftime('%F %T')}] baud={b} avg_loss≈{avg_loss:.3f}%\n")
        sys.stdout.flush()

        # judge stable
        if avg_loss <= args.loss_threshold:
            best = (b, avg_loss)

    if best:
        print(f"\n[RESULT] Max stable baud = {best[0]}  (avg_loss≈{best[1]:.3f}%, threshold={args.loss_threshold}%)")
    else:
        print("\n[RESULT] No baud met the threshold. Try lower list or improve RS485 timing/termination.")

if __name__ == "__main__":
    main()

