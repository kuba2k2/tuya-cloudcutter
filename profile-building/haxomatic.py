import os.path
import sys


class CodePatternFinder(object):
    def __init__(self, code: bytes, base_address: int = 0):
        self.code = code
        self.base_address = base_address

    def bytecode_search(self, bytecode: bytes, stop_at_first: bool = True):
        offset = self.code.find(bytecode, 0)

        if offset == -1:
            return []

        matches = [self.base_address + offset]
        if stop_at_first:
            return matches

        offset = self.code.find(bytecode, offset+1)
        while offset != -1:
            matches.append(self.base_address + offset)
            offset = self.code.find(bytecode, offset+1)

        return matches

    def set_final_thumb_offset(self, address):
        # Because we're only scanning the app partition, we must add the offset for the bootloader
        # Also add an offset of 1 for the THUMB
        return address + 0x10000 + 1


def name_output_file(desired_appended_name):
    # File generated by bk7321tools dissect_dump
    if appcode_path.endswith('app_1.00_decrypted.bin'):
        return appcode_path.replace('app_1.00_decrypted.bin', desired_appended_name)
    return appcode_path + "_" + desired_appended_name


def walk_app_code():
    print(f"[+] Searching for known exploit patterns")
    if b'TUYA' not in appcode:
        raise RuntimeError('[!] App binary does not appear to be correctly decrypted, or has no Tuya references.')
        
    # Older versions of BK7231T, BS version 30.0x, SDK 2.0.0
    if b'TUYA IOT SDK V:2.0.0' in appcode and b'AT 8710_2M' in appcode:
        # 04 1e 07 d1 11 9b 21 1c 00 is the byte pattern for datagram payload
        # 3 matches, 2nd is correct
        # 2b 68 30 1c 98 47 is the byte pattern for finish addess
        # 1 match should be found
        process_generic("BK7231T", 1, "datagram", "041e07d1119b211c00", 3, 1, "2b68301c9847", 1, 0)
        return

    # Newer versions of BK7231T, BS 40.00, SDK 1.0.x
    if b'TUYA IOT SDK V:1.0.' in appcode and b'AT bk7231t' in appcode:
        # a1 4f 06 1e is the byte pattern for datagram payload
        # 1 match should be found
        # 23 68 38 1c 98 47 is the byte pattern for finish addess
        # 2 matches should be found, 1st is correct
        process_generic("BK7231T", 2, "datagram", "a14f061e", 1, 0, "2368381c9847", 2, 0)
        return

    # Newest versions of BK7231T, BS 40.00, SDK 2.3.2
    if b'TUYA IOT SDK V:2.3.2 BS:40.00_PT:2.2_LAN:3.3_CAD:1.0.4_CD:1.0.0' in appcode:
        # TODO: Figure out how to process this format
        raise RuntimeError("This device uses SDK 2.3.2 and there is currently no pattern to mach it.")
        # process_generic("BK7231T", 3, "", "041e00d10ce7", 1, 0, "", 0, 0)
        return

    # BK7231N, BS 40.00, SDK 2.3.1
    # 0.0.2 is also a variant of 2.3.1
    if (b'TUYA IOT SDK V:2.3.1 BS:40.00_PT:2.2_LAN:3.3_CAD:1.0.3_CD:1.0.0' in appcode
            or b'TUYA IOT SDK V:0.0.2 BS:40.00_PT:2.2_LAN:3.3_CAD:1.0.3_CD:1.0.0' in appcode):
        # 05 1e 00 d1 15 e7 is the byte pattern for ssid payload
        # 1 match should be found
        # 43 68 20 1c 98 47 is the byte pattern for finish address
        # 1 match should be found
        process_generic("BK7231N", 1, "ssid", "051e00d115e7", 1, 0, "4368201c9847", 1, 0)
        return

    # BK7231N, BS 40.00, SDK 2.3.3
    if b'TUYA IOT SDK V:2.3.3 BS:40.00_PT:2.2_LAN:3.4_CAD:1.0.5_CD:1.0.0' in appcode:
        # 05 1e 00 d1 fc e6 is the byte pattern for ssid payload
        # 1 match should be found
        # 43 68 20 1c 98 47 is the byte pattern for finish address
        # 1 match should be found
        process_generic("BK7231N", 2, "ssid", "051e00d1fce6", 1, 0, "4368201c9847", 1, 0)
        return

    raise RuntimeError('Unknown pattern, please open a new issue and include the bin.')


def process_generic(chipset, pattern_version, payload_type, payload_string, payload_count, payload_index, finish_string, finish_count, finish_index):
    matcher = CodePatternFinder(appcode, 0x0)
    print(f"[+] Matched pattern for {chipset} version {pattern_version}, payload type {payload_type}")

    print(f"[+] Searching for {payload_type} payload address")
    payload_bytecode = bytes.fromhex(payload_string)
    payload_matches = matcher.bytecode_search(payload_bytecode, stop_at_first=False)
    if not payload_matches or len(payload_matches) != payload_count:
        raise RuntimeError(f"[!] Failed to find {payload_type} payload address (found {len(payload_matches)}, expected {payload_count})")
    payload_addr = matcher.set_final_thumb_offset(payload_matches[payload_index])
    for b in payload_addr.to_bytes(3, byteorder='little'):
        if b == 0:
            raise RuntimeError(f"[!] {payload_type} payload address contains a null byte, unable to continue")
    print(f"[+] {payload_type} payload address gadget (THUMB): 0x{payload_addr:X}")

    print("[+] Searching for finish address")
    finish_bytecode = bytes.fromhex(finish_string)
    finish_matches = matcher.bytecode_search(finish_bytecode, stop_at_first=False)
    if not finish_matches or len(finish_matches) > finish_count:
        raise RuntimeError("[!] Failed to find finish address")
    finish_addr = matcher.set_final_thumb_offset(finish_matches[finish_index])
    for b in finish_addr.to_bytes(3, byteorder='little'):
        if b == 0:
            if finish_count > 0:
                print("[!] Preferred finish address contained a null byte, using available alternative")
                finish_addr = matcher.set_final_thumb_offset(finish_matches[finish_index + 1])
            else:
                raise RuntimeError("[!] Finish address contains a null byte, unable to continue")
    print(f"[+] Finish address gadget (THUMB): 0x{finish_addr:X}")

    with open(name_output_file('chip.txt'), 'w') as f:
        f.write(f'{chipset}')
    with open(name_output_file('address_finish.txt'), 'w') as f:
        f.write(f'0x{finish_addr:X}')

    if payload_type == "datagram":
        with open(name_output_file('address_datagram.txt'), 'w') as f:
            f.write(f'0x{payload_addr:X}')
    elif payload_type == "ssid":
        with open(name_output_file('address_ssid.txt'), 'w') as f:
            f.write(f'0x{payload_addr:X}')
    elif payload_type == "passwd":
        with open(name_output_file('address_passwd.txt'), 'w') as f:
            f.write(f'0x{payload_addr:X}')


def run(decrypted_app_file: str):
    if not decrypted_app_file:
        print('Usage: python haxomatic.py <app code file>')
        sys.exit(1)

    address_finish_file = decrypted_app_file.replace('_app_1.00_decrypted.bin', '_address_finish.txt')
    if os.path.exists(address_finish_file):
        print('[+] Haxomatic has already been run')
        return

    global appcode_path, appcode
    appcode_path = decrypted_app_file
    with open(appcode_path, 'rb') as fs:
        appcode = fs.read()
        walk_app_code()


if __name__ == '__main__':
    run(sys.argv[1])
