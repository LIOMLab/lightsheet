def DataGenerator(deviceNumber,Cmd):
    """Fonction qui genere la commande complete"""


    command=[deviceNumber,Cmd]

    #Pour gerer les Cmd negatives
    if Cmd < 0:
        Cmd = pow(256,4) + Cmd

    #On genere les bits 3,4,5 et 6
    Byte_6 = Cmd /pow(256,3)
    Cmd = Cmd - pow(256,3) * Byte_6
    Byte_5 = Cmd / pow(256,2)
    Cmd = Cmd - pow(256,2) * Byte_5
    Byte_4 = Cmd / 256
    Cmd = Cmd - 256 * Byte_4
    Byte_3 = Cmd

    command.append(Byte_3)
    command.append(Byte_4)
    command.append(Byte_5)
    command.append(Byte_6)

    command=bytearray(command)

    return command


def Data2PositionMM(Data):
    """Fonction qui renvoie la position absolue en mm associee a la Data"""

    return Data*0.1905*pow(10,-3)



def replyCommand2Data(replyCmd):
    """Fonction qui renvoie la Data des 4 derniers int (reponse deja convertie sous la meme forme qu'une commande)"""

    return replyCmd[5]*pow(256,3)+replyCmd[4]*pow(256,2)+replyCmd[3]*256+replyCmd[2]




def bytes2int(bytes):
    """Fonction qui transforme les int en bytes"""

    result = 0
    for b in bytes:
        result = result * 256 + int(b)
    return result


def int2bytes(value, length):
    """Fonction qui convertit les int en bytes"""

    result = []
    for i in range(0, length):
        result.append(value >> (i * 8) & 0xff)
    result.reverse()
    return result

